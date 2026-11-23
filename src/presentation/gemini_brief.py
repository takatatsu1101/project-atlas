"""
後段AI（Gemini / Skill）連携向け 高密度ブリーフ生成・配信モジュール

将来的なクラウド実行（GitHub Actions + Google Drive API）を見据え、
ブリーフ生成（純粋レンダリング）と保存・配信（ローカルコピー / APIアップロード）を分離して設計する。
すべてのテクニカル・価格水準抽出は as_of_date 以前のバーのみを参照し、先読みバイアスを完全に遮断する。
"""

from __future__ import annotations

from contextlib import nullcontext
import json
import math
import mimetypes
import os
import shutil
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
)
from urllib.parse import quote

from pydantic import BaseModel, Field
import requests

from src.common.logger import get_logger
from src.model.data_models import (
    AnalysisResultModel,
    FinancialModel,
    IndicatorSetModel,
    MarketContextModel,
    OhlcvModel,
    SectorMetricsModel,
)

logger = get_logger(__name__)

_MA_PERIODS: Tuple[int, ...] = (5, 25, 75, 200)


def normalize_bar_date(value: Any) -> date:
    """date / datetime を date 型へ正規化する。"""
    if isinstance(value, datetime):
        return value.date()
    return value


def normalize_symbol(symbol: str) -> str:
    """銘柄コードを東証ティッカー形式（例: 7203 -> 7203.T）へ正規化する。"""
    cleaned = symbol.strip().upper()
    if not cleaned:
        return cleaned
    if "." in cleaned:
        return cleaned
    return f"{cleaned}.T"


class MovingAverageMetrics(BaseModel):
    """移動平均線の現在値・乖離率・傾き指標"""

    period: int
    value: Optional[float] = None
    deviation_pct: Optional[float] = None
    slope_5d_pct: Optional[float] = None
    slope_label: str = "N/A"


class OhlcvCompactRow(BaseModel):
    """直近15営業日コンパクトOHLCV表の1行"""

    date: date
    open: float
    high: float
    low: float
    close: float
    change_pct: Optional[float] = None
    volume_ratio: Optional[float] = None


class GeminiStockBriefData(BaseModel):
    """Gemini ブリーフ出力用の1銘柄分の統合判断材料"""

    result: AnalysisResultModel
    is_watch_symbol: bool = False
    data_missing: bool = False
    unit_capital: Optional[float] = None
    avg_trading_value_20d_oku: Optional[float] = None
    gap_up_limit_price: Optional[float] = None
    atr14: Optional[float] = None
    atr14_pct: Optional[float] = None
    volume_ratio: Optional[float] = None
    ma_metrics: List[MovingAverageMetrics] = Field(default_factory=list)
    high_20d: Optional[float] = None
    low_20d: Optional[float] = None
    high_60d: Optional[float] = None
    low_60d: Optional[float] = None
    high_250d: Optional[float] = None
    low_250d: Optional[float] = None
    swing_high: Optional[float] = None
    swing_high_date: Optional[date] = None
    swing_low: Optional[float] = None
    swing_low_date: Optional[date] = None
    poc_60d: Optional[float] = None
    recent_ohlcv: List[OhlcvCompactRow] = Field(default_factory=list)
    financial_detail: Dict[str, Any] = Field(default_factory=dict)
    rs_percentile: Optional[float] = None
    sector_momentum_score: Optional[float] = None
    relative_valuation_z: Optional[float] = None
    relative_valuation_score: Optional[float] = None


DeliveryTarget = Union[Path, str]


class GoogleDriveDeliveryError(RuntimeError):
    """Google Drive API を用いたブリーフ配信処理の失敗を表す例外。"""


class BriefDeliveryBackend(Protocol):
    """ブリーフファイル配信バックエンドの抽象プロトコル（方式A: ローカルコピー / 方式B: Drive API）"""

    def deliver(
        self, files: Dict[str, Path], as_of_date: date
    ) -> Dict[str, DeliveryTarget]:
        """生成されたブリーフファイルを配信先へ配置し、成功したキーと出力先（Path または URI 等）を返す。"""
        ...


class LocalCopyBriefDelivery:
    """方式A: Google ドライブ デスクトップ同期フォルダ等のローカルディレクトリへコピーする配信実装"""

    key_suffix: str = "copy"

    def __init__(self, copy_dir: Union[str, Path]):
        self.copy_dir = Path(copy_dir).expanduser()

    def deliver(
        self, files: Dict[str, Path], as_of_date: date
    ) -> Dict[str, Path]:
        """
        同期先ディレクトリへファイルをコピーする。
        未マウントや権限エラー等で書き込みできない場合は警告ログに留め、例外を送出しない。
        """
        delivered: Dict[str, Path] = {}
        try:
            # Google Drive 未マウント時などに /Volumes/... 配下を誤生成しないよう親マウントを確認
            if not self.copy_dir.exists():
                parent = self.copy_dir.parent
                if not parent.exists():
                    logger.warning(
                        f"Google ドライブ同期先の親ディレクトリが存在しないためコピーをスキップします: {self.copy_dir}"
                    )
                    return delivered
                self.copy_dir.mkdir(parents=True, exist_ok=True)

            if not self.copy_dir.is_dir():
                logger.warning(
                    f"コピー先がディレクトリではないためスキップします: {self.copy_dir}"
                )
                return delivered

            for key, src_path in files.items():
                if not src_path.exists():
                    continue
                dst_path = self.copy_dir / src_path.name
                shutil.copy2(src_path, dst_path)
                delivered[key] = dst_path
        except OSError as e:
            logger.warning(
                f"ブリーフの同期フォルダコピーに失敗しました（ローカル出力は成功しています）[{self.copy_dir}]: {e}"
            )
            return delivered

        return delivered


def _escape_drive_query_literal(value: str) -> str:
    """Google Drive API v3 の q パラメータ文字列リテラル用にバックスラッシュとシングルクォートをエスケープする。"""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _resolve_upload_mime_type(src_path: Path) -> str:
    """配信対象ファイルの拡張子に応じた純粋な MIME タイプ（パラメータなし）を解決する。"""
    if src_path.suffix.lower() in (".md", ".markdown"):
        return "text/markdown"
    guessed, _ = mimetypes.guess_type(src_path.name)
    return guessed or "application/octet-stream"


def _build_multipart_related_body(
    metadata: Dict[str, Any],
    content: bytes,
    content_type: str = "text/markdown; charset=utf-8",
    boundary: Optional[str] = None,
) -> Tuple[bytes, str]:
    """Google Drive REST API v3 uploadType=multipart 向けの multipart/related ボディと境界文字列を構築する。"""
    meta_bytes = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    if boundary is not None:
        resolved_boundary = boundary
    else:
        while True:
            candidate = f"atlas_drive_{uuid.uuid4().hex}"
            candidate_bytes = candidate.encode("ascii")
            if candidate_bytes not in meta_bytes and candidate_bytes not in content:
                resolved_boundary = candidate
                break

    b_bytes = resolved_boundary.encode("ascii")
    body = b"".join(
        [
            b"--",
            b_bytes,
            b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n",
            meta_bytes,
            b"\r\n--",
            b_bytes,
            b"\r\nContent-Type: ",
            content_type.encode("utf-8"),
            b"\r\n\r\n",
            content,
            b"\r\n--",
            b_bytes,
            b"--\r\n",
        ]
    )
    return body, resolved_boundary


def _extract_safe_error_detail(response: requests.Response) -> str:
    """HTTP エラーレスポンスから機密値を含めない安全なエラー要約を抽出する。"""
    status = getattr(response, "status_code", "unknown")
    try:
        payload = response.json()
    except ValueError:
        reason = getattr(response, "reason", None)
        if isinstance(reason, str) and reason.strip():
            return f"HTTP {status} ({reason.strip()[:120]})"
        return f"HTTP {status}"

    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            msg = err.get("message")
            if isinstance(msg, str) and msg.strip():
                return f"HTTP {status}: {msg.strip()[:300]}"
        elif isinstance(err, str) and err.strip():
            desc = payload.get("error_description")
            if isinstance(desc, str) and desc.strip():
                return f"HTTP {status}: {err.strip()[:100]} ({desc.strip()[:200]})"
            return f"HTTP {status}: {err.strip()[:200]}"
        msg = payload.get("message")
        if isinstance(msg, str) and msg.strip():
            return f"HTTP {status}: {msg.strip()[:300]}"
    return f"HTTP {status}"


class GoogleDriveBriefDelivery:
    """方式B: OAuth 2.0 と Google Drive REST API v3（requests 直接実装）でマイドライブへ配信する実装"""

    key_suffix: str = "drive"
    _TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    _FILES_URL: str = "https://www.googleapis.com/drive/v3/files"
    _UPLOAD_URL: str = "https://www.googleapis.com/upload/drive/v3/files"
    _ENV_VAR_CLIENT_ID: str = "GOOGLE_DRIVE_CLIENT_ID"
    _ENV_VAR_CLIENT_SECRET: str = "GOOGLE_DRIVE_CLIENT_SECRET"
    _ENV_VAR_REFRESH_TOKEN: str = "GOOGLE_DRIVE_REFRESH_TOKEN"
    _ENV_VAR_FOLDER_ID: str = "GOOGLE_DRIVE_FOLDER_ID"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        folder_id: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        session: Optional[requests.Session] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ):
        required_fields = (
            ("client_id", client_id),
            ("client_secret", client_secret),
            ("refresh_token", refresh_token),
            ("folder_id", folder_id),
        )
        empty_names = [
            name
            for name, raw in required_fields
            if not isinstance(raw, str) or not raw.strip()
        ]
        if empty_names:
            raise ValueError(
                f"Google Drive 配信の必須パラメータが未設定または空です: {', '.join(empty_names)}"
            )

        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or timeout <= 0
        ):
            raise ValueError(f"timeout は有限の正の数値を指定してください: {timeout}")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError(f"max_retries は 0 以上の整数を指定してください: {max_retries}")
        if (
            isinstance(backoff_base, bool)
            or not isinstance(backoff_base, (int, float))
            or not math.isfinite(float(backoff_base))
            or backoff_base < 0
        ):
            raise ValueError(f"backoff_base は有限の 0 以上の数値を指定してください: {backoff_base}")

        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.refresh_token = refresh_token.strip()
        self.folder_id = folder_id.strip()
        self.timeout = float(timeout)
        self.max_retries = max_retries
        self.backoff_base = float(backoff_base)
        self._session = session
        self._sleep_fn = sleep_fn or time.sleep

    @classmethod
    def from_env(
        cls,
        folder_id: Optional[str] = None,
        environ: Optional[Mapping[str, str]] = None,
        **kwargs: Any,
    ) -> "GoogleDriveBriefDelivery":
        """環境変数（GOOGLE_DRIVE_*）から設定を読み込み、GoogleDriveBriefDelivery を生成する。"""
        env = environ if environ is not None else os.environ
        resolved_folder = (
            folder_id.strip()
            if isinstance(folder_id, str) and folder_id.strip()
            else str(env.get(cls._ENV_VAR_FOLDER_ID, "") or "").strip()
        )
        client_id = str(env.get(cls._ENV_VAR_CLIENT_ID, "") or "").strip()
        client_secret = str(env.get(cls._ENV_VAR_CLIENT_SECRET, "") or "").strip()
        refresh_token = str(env.get(cls._ENV_VAR_REFRESH_TOKEN, "") or "").strip()

        missing_vars = [
            env_name
            for env_name, val in (
                (cls._ENV_VAR_CLIENT_ID, client_id),
                (cls._ENV_VAR_CLIENT_SECRET, client_secret),
                (cls._ENV_VAR_REFRESH_TOKEN, refresh_token),
                (cls._ENV_VAR_FOLDER_ID, resolved_folder),
            )
            if not val
        ]
        if missing_vars:
            raise ValueError(
                f"Google Drive 配信に必要な環境変数が未設定です: {', '.join(missing_vars)}"
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            folder_id=resolved_folder,
            **kwargs,
        )

    def _redact_secrets(self, text: str, extra_secrets: Sequence[str] = ()) -> str:
        """エラー文言から認証シークレット・トークン文字列を確実に除去する。"""
        sanitized = text
        for secret in (
            self.client_secret,
            self.refresh_token,
            *extra_secrets,
        ):
            if secret:
                sanitized = sanitized.replace(secret, "***")
        return sanitized

    def _request_with_retry(
        self,
        session: requests.Session,
        method: str,
        url: str,
        *,
        operation: str,
        extra_secrets: Sequence[str] = (),
        **kwargs: Any,
    ) -> requests.Response:
        """ネットワーク例外・429・5xx に対して指数バックオフ付きでリトライし、非2xx時は GoogleDriveDeliveryError を送出する。"""
        kwargs.setdefault("timeout", self.timeout)

        for attempt in range(self.max_retries + 1):
            try:
                resp = session.request(method, url, **kwargs)
            except requests.RequestException as e:
                safe_err = self._redact_secrets(str(e), extra_secrets=extra_secrets)
                if attempt < self.max_retries:
                    delay = self.backoff_base * (2**attempt)
                    logger.warning(
                        f"Google Drive API {operation} で通信例外が発生したためリトライします "
                        f"({attempt + 1}/{self.max_retries}, 待機={delay:.1f}s): {safe_err}"
                    )
                    self._sleep_fn(delay)
                    continue
                raise GoogleDriveDeliveryError(
                    f"Google Drive API {operation} に失敗しました（リトライ上限到達）: {safe_err}"
                ) from e

            status = resp.status_code
            if 200 <= status < 300:
                return resp

            detail = self._redact_secrets(
                _extract_safe_error_detail(resp), extra_secrets=extra_secrets
            )
            is_retryable = status == 429 or 500 <= status < 600
            if is_retryable and attempt < self.max_retries:
                delay = self.backoff_base * (2**attempt)
                logger.warning(
                    f"Google Drive API {operation} が一時エラーを返したためリトライします "
                    f"({attempt + 1}/{self.max_retries}, 待機={delay:.1f}s): {detail}"
                )
                self._sleep_fn(delay)
                continue

            raise GoogleDriveDeliveryError(
                f"Google Drive API {operation} に失敗しました: {detail}"
            )

        raise GoogleDriveDeliveryError(f"Google Drive API {operation} に失敗しました。")

    def _fetch_access_token(self, session: requests.Session) -> str:
        """リフレッシュトークンを用いて OAuth 2.0 アクセストークンを取得する。"""
        resp = self._request_with_retry(
            session,
            "POST",
            self._TOKEN_URL,
            operation="OAuthトークン取得",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        try:
            payload = resp.json()
        except ValueError as e:
            raise GoogleDriveDeliveryError(
                "Google OAuth トークン応答の JSON 解析に失敗しました。"
            ) from e

        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise GoogleDriveDeliveryError(
                "Google OAuth トークン応答に有効な access_token が含まれていません。"
            )
        return token.strip()

    def _find_existing_file_id(
        self,
        session: requests.Session,
        access_token: str,
        file_name: str,
    ) -> Optional[str]:
        """指定フォルダ配下から未削除の同名ファイルを検索し、存在すれば最新更新の fileId を返す。"""
        escaped_name = _escape_drive_query_literal(file_name)
        escaped_folder = _escape_drive_query_literal(self.folder_id)
        query = f"name = '{escaped_name}' and '{escaped_folder}' in parents and trashed = false"
        resp = self._request_with_retry(
            session,
            "GET",
            self._FILES_URL,
            operation=f"同名ファイル検索({file_name})",
            extra_secrets=(access_token,),
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "q": query,
                "fields": "files(id, name, modifiedTime)",
                "orderBy": "modifiedTime desc",
                "pageSize": 10,
                "spaces": "drive",
            },
        )
        try:
            payload = resp.json()
        except ValueError as e:
            raise GoogleDriveDeliveryError(
                f"Google Drive ファイル検索応答の JSON 解析に失敗しました ({file_name})。"
            ) from e

        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, list) or not files:
            return None

        if len(files) > 1:
            logger.warning(
                f"Google ドライブ指定フォルダ内に同名ファイルが {len(files)} 件存在するため最新ファイルへ上書き更新します: {file_name}"
            )

        first = files[0]
        file_id = first.get("id") if isinstance(first, dict) else None
        if not isinstance(file_id, str) or not file_id.strip():
            return None
        return file_id.strip()

    def _upload_file(
        self,
        session: requests.Session,
        access_token: str,
        src_path: Path,
        existing_file_id: Optional[str],
    ) -> str:
        """対象ファイルを Google Drive へ新規作成（POST）または上書き更新（PATCH）する。"""
        mime_type = _resolve_upload_mime_type(src_path)
        content = src_path.read_bytes()
        if existing_file_id:
            # Drive API v3 では PATCH のメタデータに parents を含めるとエラーになるため除外する
            metadata: Dict[str, Any] = {"name": src_path.name, "mimeType": mime_type}
            method = "PATCH"
            url = f"{self._UPLOAD_URL}/{quote(existing_file_id, safe='')}"
            operation = f"ファイル上書き更新({src_path.name})"
        else:
            metadata = {
                "name": src_path.name,
                "parents": [self.folder_id],
                "mimeType": mime_type,
            }
            method = "POST"
            url = self._UPLOAD_URL
            operation = f"ファイル新規作成({src_path.name})"

        part_content_type = (
            f"{mime_type}; charset=utf-8" if mime_type.startswith("text/") else mime_type
        )
        body, boundary = _build_multipart_related_body(
            metadata=metadata,
            content=content,
            content_type=part_content_type,
        )
        resp = self._request_with_retry(
            session,
            method,
            url,
            operation=operation,
            extra_secrets=(access_token,),
            params={"uploadType": "multipart", "fields": "id,name"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            data=body,
        )
        try:
            payload = resp.json()
        except ValueError as e:
            raise GoogleDriveDeliveryError(
                f"Google Drive アップロード応答の JSON 解析に失敗しました ({src_path.name})。"
            ) from e

        file_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(file_id, str) or not file_id.strip():
            raise GoogleDriveDeliveryError(
                f"Google Drive アップロード応答にファイル ID が含まれていません ({src_path.name})。"
            )
        return file_id.strip()

    def deliver(
        self, files: Dict[str, Path], as_of_date: date
    ) -> Dict[str, DeliveryTarget]:
        """実在するブリーフファイルを指定 Google ドライブフォルダへアップロードし、gdrive://<fileId> マップを返す。"""
        target_files = [
            (key, src_path) for key, src_path in files.items() if src_path.exists()
        ]
        if not target_files:
            return {}

        delivered: Dict[str, DeliveryTarget] = {}
        session_cm = (
            nullcontext(self._session)
            if self._session is not None
            else requests.Session()
        )
        with session_cm as session:
            access_token = self._fetch_access_token(session)
            for key, src_path in target_files:
                existing_id = self._find_existing_file_id(
                    session, access_token, src_path.name
                )
                file_id = self._upload_file(session, access_token, src_path, existing_id)
                delivered[key] = f"gdrive://{file_id}"
                action_label = "上書き更新" if existing_id else "新規作成"
                logger.info(
                    f"Google ドライブへブリーフを{action_label}しました: {src_path.name} -> gdrive://{file_id}"
                )

        return delivered


def _classify_slope_label(slope_pct: Optional[float]) -> str:
    if slope_pct is None:
        return "N/A"
    if slope_pct > 0.3:
        return "上向き"
    if slope_pct < -0.3:
        return "下向き"
    return "横ばい"


def compute_recent_swing_levels(
    ohlcv_slice: Sequence[OhlcvModel],
    lookback_bars: int = 120,
    pivot_window: int = 3,
) -> Tuple[Optional[float], Optional[date], Optional[float], Optional[date]]:
    """
    as_of_date 以前の OHLCV スライスから、確定済みの直近スイング高値（戻り高値）・スイング安値（押し安値）を抽出する。
    右側 pivot_window 本がすべてスライス内に存在するピボットのみを確定扱いとし、先読みを完全に遮断する。
    """
    if not ohlcv_slice or lookback_bars <= 0 or pivot_window <= 0:
        return None, None, None, None

    window = list(ohlcv_slice[-lookback_bars:])
    n = len(window)
    if n < pivot_window * 2 + 1:
        return None, None, None, None

    swing_high: Optional[float] = None
    swing_high_date: Optional[date] = None
    swing_low: Optional[float] = None
    swing_low_date: Optional[date] = None

    for i in range(pivot_window, n - pivot_window):
        sub = window[i - pivot_window : i + pivot_window + 1]
        bar = window[i]
        bar_d = normalize_bar_date(bar.date)
        if bar.high >= max(b.high for b in sub):
            swing_high = float(bar.high)
            swing_high_date = bar_d
        if bar.low <= min(b.low for b in sub):
            swing_low = float(bar.low)
            swing_low_date = bar_d

    return swing_high, swing_high_date, swing_low, swing_low_date


def compute_volume_poc(
    ohlcv_slice: Sequence[OhlcvModel],
    lookback_bars: int = 60,
    bins: int = 20,
) -> Optional[float]:
    """
    直近 lookback_bars 営業日の価格帯別出来高 POC（Point of Control）を算出する。
    各バーの代表価格 (high + low + close) / 3 に出来高を集計し、最大出来高ビンの中心価格を返す。
    """
    if not ohlcv_slice or lookback_bars <= 0 or bins <= 0:
        return None

    window = list(ohlcv_slice[-lookback_bars:])
    if not window:
        return None

    min_price = min(float(b.low) for b in window)
    max_price = max(float(b.high) for b in window)
    if max_price <= min_price:
        return float(window[-1].close)

    step = (max_price - min_price) / bins
    if step <= 0:
        return float(window[-1].close)

    hist = [0.0] * bins
    for b in window:
        typical = (float(b.high) + float(b.low) + float(b.close)) / 3.0
        idx = int((typical - min_price) / step)
        idx = max(0, min(bins - 1, idx))
        hist[idx] += float(b.volume)

    best_idx = max(range(bins), key=lambda k: hist[k])
    if hist[best_idx] <= 0:
        return float(window[-1].close)

    return min_price + (best_idx + 0.5) * step


def _compute_sma_series(closes: Sequence[float], period: int) -> List[Optional[float]]:
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period or period <= 0:
        return out
    running = sum(closes[:period])
    out[period - 1] = running / period
    for i in range(period, n):
        running += closes[i] - closes[i - period]
        out[i] = running / period
    return out


def _compute_atr14_fallback(ohlcv_slice: Sequence[OhlcvModel]) -> Optional[float]:
    if len(ohlcv_slice) < 15:
        return None
    trs: List[float] = []
    for i in range(len(ohlcv_slice) - 14, len(ohlcv_slice)):
        cur = ohlcv_slice[i]
        prev = ohlcv_slice[i - 1]
        tr = max(
            float(cur.high) - float(cur.low),
            abs(float(cur.high) - float(prev.close)),
            abs(float(cur.low) - float(prev.close)),
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else None


def _extract_financial_detail(
    result: AnalysisResultModel,
    financial_data: Optional[FinancialModel],
) -> Dict[str, Any]:
    detail: Dict[str, Any] = dict(result.financial_summary or {})
    if financial_data is not None:
        mapping = {
            "per": financial_data.per,
            "pbr": financial_data.pbr,
            "roe": financial_data.roe,
            "equity_ratio": financial_data.equity_ratio,
            "revenue_growth": financial_data.revenue_growth,
            "revenue_growth_3y_avg": financial_data.revenue_growth_3y_avg,
            "net_profit_growth": financial_data.net_profit_growth,
            "net_profit_growth_3y_avg": financial_data.net_profit_growth_3y_avg,
            "operating_cf": financial_data.operating_cf,
            "free_cash_flow": financial_data.free_cash_flow,
            "operating_cf_margin": financial_data.operating_cf_margin,
            "dividend_per_share": financial_data.dividend_per_share,
            "payout_ratio": financial_data.payout_ratio,
            "total_payout_ratio": financial_data.total_payout_ratio,
            "share_buyback": financial_data.share_buyback,
            "consecutive_dividend_increase_years": financial_data.consecutive_dividend_increase_years,
            "fiscal_date": (
                financial_data.fiscal_date.isoformat()
                if financial_data.fiscal_date is not None
                else None
            ),
        }
        for k, v in mapping.items():
            if v is not None:
                detail[k] = v
    return detail


def build_gemini_stock_brief_data(
    result: AnalysisResultModel,
    ohlcv_list: Sequence[OhlcvModel],
    indicator_sets: Optional[Sequence[IndicatorSetModel]] = None,
    financial_data: Optional[FinancialModel] = None,
    market_context: Optional[MarketContextModel] = None,
    as_of_date: Optional[date] = None,
    is_watch_symbol: bool = False,
) -> GeminiStockBriefData:
    """
    1銘柄分の OHLCV・指標・財務・MarketContext から、Gemini ブリーフ用の判断材料を構築する。
    as_of_date が指定された場合は、関数内部でも as_of_date 以前のバーのみに防御的スライスする。
    """
    resolved_as_of = normalize_bar_date(as_of_date) if as_of_date is not None else None
    if resolved_as_of is not None:
        eligible_ohlcv = [
            b for b in ohlcv_list if normalize_bar_date(b.date) <= resolved_as_of
        ]
    else:
        eligible_ohlcv = list(ohlcv_list)
    eligible_ohlcv.sort(key=lambda b: normalize_bar_date(b.date))

    if not eligible_ohlcv:
        return GeminiStockBriefData(
            result=result,
            is_watch_symbol=is_watch_symbol,
            data_missing=True,
            financial_detail=_extract_financial_detail(result, financial_data),
        )

    latest_bar = eligible_ohlcv[-1]
    latest_close = float(latest_bar.close)
    closes = [float(b.close) for b in eligible_ohlcv]

    # 20日平均売買代金（億円）
    recent_20 = eligible_ohlcv[-20:]
    avg_tv_20 = (
        sum(float(b.close) * float(b.volume) for b in recent_20) / len(recent_20)
        if recent_20
        else None
    )
    avg_tv_20_oku = (avg_tv_20 / 100_000_000.0) if avg_tv_20 is not None else None

    # 出来高倍率（当日 / 過去25営業日平均、当日除外）
    prev_25 = eligible_ohlcv[-26:-1] if len(eligible_ohlcv) >= 2 else []
    avg_vol_25 = (
        sum(float(b.volume) for b in prev_25) / len(prev_25) if prev_25 else None
    )
    vol_ratio = (
        (float(latest_bar.volume) / avg_vol_25)
        if (avg_vol_25 is not None and avg_vol_25 > 0)
        else None
    )

    # 指標セットを as_of_date 以下で日付順に整理
    sorted_inds: List[IndicatorSetModel] = []
    if indicator_sets:
        if resolved_as_of is not None:
            sorted_inds = [
                ind
                for ind in indicator_sets
                if normalize_bar_date(ind.date) <= resolved_as_of
            ]
        else:
            sorted_inds = list(indicator_sets)
        sorted_inds.sort(key=lambda ind: normalize_bar_date(ind.date))

    latest_ind = sorted_inds[-1].indicators if sorted_inds else {}
    atr14 = latest_ind.get("ATR14")
    if atr14 is None:
        atr14 = _compute_atr14_fallback(eligible_ohlcv)
    atr14_pct = (
        (float(atr14) / latest_close * 100.0)
        if (atr14 is not None and latest_close > 0)
        else None
    )

    # SMA5 / 25 / 75 / 200（価格・乖離率・5日傾き）
    ma_metrics: List[MovingAverageMetrics] = []
    for period in _MA_PERIODS:
        key = f"SMA{period}"
        ind_series = [
            ind.indicators.get(key)
            for ind in sorted_inds
            if ind.indicators.get(key) is not None
        ]
        if len(ind_series) >= 1 and len(sorted_inds) == len(eligible_ohlcv):
            series_vals: List[Optional[float]] = [
                ind.indicators.get(key) for ind in sorted_inds
            ]
        else:
            series_vals = _compute_sma_series(closes, period)

        cur_val = series_vals[-1] if series_vals else None
        if cur_val is None and key in latest_ind:
            cur_val = latest_ind.get(key)

        dev_pct: Optional[float] = None
        if cur_val is not None and cur_val > 0:
            dev_pct = (latest_close - float(cur_val)) / float(cur_val) * 100.0

        slope_5d_pct: Optional[float] = None
        if len(series_vals) >= 6:
            prev_val = series_vals[-6]
            if cur_val is not None and prev_val is not None and prev_val > 0:
                slope_5d_pct = (float(cur_val) - float(prev_val)) / float(prev_val) * 100.0

        ma_metrics.append(
            MovingAverageMetrics(
                period=period,
                value=float(cur_val) if cur_val is not None else None,
                deviation_pct=dev_pct,
                slope_5d_pct=slope_5d_pct,
                slope_label=_classify_slope_label(slope_5d_pct),
            )
        )

    # 20 / 60 / 250 日 高値・安値
    def _range_hl(bars: Sequence[OhlcvModel]) -> Tuple[Optional[float], Optional[float]]:
        if not bars:
            return None, None
        return max(float(b.high) for b in bars), min(float(b.low) for b in bars)

    high_20d, low_20d = _range_hl(eligible_ohlcv[-20:])
    high_60d, low_60d = _range_hl(eligible_ohlcv[-60:])
    high_250d, low_250d = _range_hl(eligible_ohlcv[-250:])

    # スイング高安・60日POC
    swing_high, swing_high_date, swing_low, swing_low_date = (
        compute_recent_swing_levels(eligible_ohlcv)
    )
    poc_60d = compute_volume_poc(eligible_ohlcv, lookback_bars=60, bins=20)

    # 直近15営業日コンパクト OHLCV
    n_total = len(eligible_ohlcv)
    start_idx = max(0, n_total - 15)
    recent_rows: List[OhlcvCompactRow] = []
    for idx in range(start_idx, n_total):
        bar = eligible_ohlcv[idx]
        change_pct: Optional[float] = None
        if idx > 0:
            prev_c = float(eligible_ohlcv[idx - 1].close)
            if prev_c > 0:
                change_pct = (float(bar.close) - prev_c) / prev_c * 100.0

        prev_window = eligible_ohlcv[max(0, idx - 25) : idx]
        row_vol_ratio: Optional[float] = None
        if prev_window:
            avg_v = sum(float(b.volume) for b in prev_window) / len(prev_window)
            if avg_v > 0:
                row_vol_ratio = float(bar.volume) / avg_v

        recent_rows.append(
            OhlcvCompactRow(
                date=normalize_bar_date(bar.date),
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                change_pct=change_pct,
                volume_ratio=row_vol_ratio,
            )
        )

    # MarketContext からの相対評価抽出
    rs_pct: Optional[float] = None
    sec_mom: Optional[float] = None
    rel_val_z: Optional[float] = None
    rel_val_score: Optional[float] = None
    if market_context is not None and market_context.is_active:
        sym_metrics = market_context.symbol_metrics.get(
            result.symbol
        ) or market_context.symbol_metrics.get(normalize_symbol(result.symbol))
        if sym_metrics is not None:
            rs_pct = sym_metrics.rs_percentile
            sec_mom = sym_metrics.sector_momentum_score
            rel_val_z = sym_metrics.relative_valuation_z
            rel_val_score = sym_metrics.relative_valuation_score

    return GeminiStockBriefData(
        result=result,
        is_watch_symbol=is_watch_symbol,
        data_missing=False,
        unit_capital=latest_close * 100.0,
        avg_trading_value_20d_oku=avg_tv_20_oku,
        gap_up_limit_price=latest_close * 1.03,
        atr14=float(atr14) if atr14 is not None else None,
        atr14_pct=atr14_pct,
        volume_ratio=vol_ratio,
        ma_metrics=ma_metrics,
        high_20d=high_20d,
        low_20d=low_20d,
        high_60d=high_60d,
        low_60d=low_60d,
        high_250d=high_250d,
        low_250d=low_250d,
        swing_high=swing_high,
        swing_high_date=swing_high_date,
        swing_low=swing_low,
        swing_low_date=swing_low_date,
        poc_60d=poc_60d,
        recent_ohlcv=recent_rows,
        financial_detail=_extract_financial_detail(result, financial_data),
        rs_percentile=rs_pct,
        sector_momentum_score=sec_mom,
        relative_valuation_z=rel_val_z,
        relative_valuation_score=rel_val_score,
    )


def _fmt_num(val: Optional[float], fmt: str = ",.1f", suffix: str = "") -> str:
    if val is None:
        return "N/A"
    return f"{val:{fmt}}{suffix}"


def _fmt_yen(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    return f"{val:,.0f}円"


def _fmt_pct(val: Optional[float], signed: bool = True) -> str:
    if val is None:
        return "N/A"
    if signed:
        return f"{val:+.2f}%"
    return f"{val:.2f}%"


def _render_market_section(
    market_context: Optional[MarketContextModel],
) -> List[str]:
    lines: List[str] = ["## 1. 市場環境・33業種ローテーション", ""]
    if market_context is None or not market_context.is_active:
        reason = (
            market_context.inactive_reason
            if market_context is not None and market_context.inactive_reason
            else "市場コンテキスト未算出（少数銘柄または無効設定）"
        )
        lines.append(f"- 状態: 無効 / 中立フォールバック（理由: {reason}）")
        lines.append("")
        return lines

    breadth_str = (
        f"{market_context.breadth_ratio * 100.0:.1f}%"
        if market_context.breadth_ratio is not None
        else "N/A"
    )
    lines.append(
        f"- **地合いレジーム**: `{market_context.regime}` | "
        f"**Breadth (close > SMA25)**: {breadth_str} "
        f"({market_context.above_sma25_count}/{market_context.valid_sma25_count}, "
        f"ユニバース {market_context.universe_size}銘柄)"
    )
    if (
        market_context.breakout_threshold_delta > 0
        or market_context.breakout_score_penalty > 0
    ):
        lines.append(
            f"- **地合いガード**: ブレイクアウト要求閾値 `+{market_context.breakout_threshold_delta:.1f}` / "
            f"減点 `-{market_context.breakout_score_penalty:.1f}`"
        )

    bm = market_context.benchmark
    if bm is not None and bm.close is not None:
        sma25_pos = (
            "上" if bm.above_sma25 is True else ("下" if bm.above_sma25 is False else "N/A")
        )
        sma75_pos = (
            "上" if bm.above_sma75 is True else ("下" if bm.above_sma75 is False else "N/A")
        )
        lines.append(
            f"- **ベンチマーク (`{bm.symbol}`)**: 終値 {_fmt_yen(bm.close)} | "
            f"SMA25({sma25_pos}): {_fmt_yen(bm.sma25)} | SMA75({sma75_pos}): {_fmt_yen(bm.sma75)} | "
            f"騰落率 20d={_fmt_pct(bm.return_20d)}, "
            f"60d={_fmt_pct(bm.return_60d)}, "
            f"120d={_fmt_pct(bm.return_120d)}"
        )

    # 33業種ランキング（上位・下位）
    sufficient_sectors: List[SectorMetricsModel] = [
        sm
        for sm in market_context.sector_metrics.values()
        if sm.is_sufficient and sm.sector_momentum_score is not None
    ]
    if sufficient_sectors:
        sufficient_sectors.sort(
            key=lambda s: float(s.sector_momentum_score or 0.0), reverse=True
        )
        top_sectors = sufficient_sectors[:5]
        bottom_sectors = list(reversed(sufficient_sectors[-5:]))

        lines.append("")
        lines.append("### 33業種モメンタム 上位（資金流入）")
        lines.append("| 順位 | 業種 | 銘柄数 | 平均20日リターン | SMA25上回り率 | モメンタムスコア |")
        lines.append("|---:|---|---:|---:|---:|---:|")
        for idx, sm in enumerate(top_sectors, start=1):
            ret20 = sm.avg_return_20d
            above25 = (
                (sm.above_sma25_ratio * 100.0)
                if sm.above_sma25_ratio is not None
                else None
            )
            lines.append(
                f"| {idx} | {sm.sector_33} | {sm.member_count} | "
                f"{_fmt_pct(ret20)} | {_fmt_pct(above25, signed=False)} | "
                f"{_fmt_num(sm.sector_momentum_score, '.1f')} |"
            )

        lines.append("")
        lines.append("### 33業種モメンタム 下位（資金流出）")
        lines.append("| 順位 | 業種 | 銘柄数 | 平均20日リターン | SMA25上回り率 | モメンタムスコア |")
        lines.append("|---:|---|---:|---:|---:|---:|")
        total_cnt = len(sufficient_sectors)
        for offset, sm in enumerate(bottom_sectors):
            rank_num = total_cnt - offset
            ret20 = sm.avg_return_20d
            above25 = (
                (sm.above_sma25_ratio * 100.0)
                if sm.above_sma25_ratio is not None
                else None
            )
            lines.append(
                f"| {rank_num} | {sm.sector_33} | {sm.member_count} | "
                f"{_fmt_pct(ret20)} | {_fmt_pct(above25, signed=False)} | "
                f"{_fmt_num(sm.sector_momentum_score, '.1f')} |"
            )

    lines.append("")
    return lines


def _render_stock_summary_table(
    items: Sequence[GeminiStockBriefData],
    include_rank: bool = True,
) -> List[str]:
    lines: List[str] = []
    if include_rank:
        lines.append(
            "| 順位 | コード | 銘柄名 | 業種 | 戦略 | 総合 | 終値 | 1単元資金 | 20日売買代金 | +3%上限 | RS順位 | 60日POC |"
        )
        lines.append("|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    else:
        lines.append(
            "| コード | 銘柄名 | 業種 | 戦略 | 総合 | 終値 | 1単元資金 | 20日売買代金 | +3%上限 | RS順位 | 60日POC |"
        )
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")

    for item in items:
        r = item.result
        close_val = r.key_levels.get("close")
        rs_str = _fmt_num(item.rs_percentile, ".1f")
        tv_str = _fmt_num(item.avg_trading_value_20d_oku, ".1f", "億")
        if include_rank:
            rank_str = str(r.rank) if r.rank is not None else "-"
            lines.append(
                f"| {rank_str} | {r.symbol} | {r.company_name} | {r.sector or '-'} | {r.strategy_type} | "
                f"{r.total_score:.1f} | {_fmt_yen(close_val)} | {_fmt_yen(item.unit_capital)} | "
                f"{tv_str} | {_fmt_yen(item.gap_up_limit_price)} | {rs_str} | {_fmt_yen(item.poc_60d)} |"
            )
        else:
            lines.append(
                f"| {r.symbol} | {r.company_name} | {r.sector or '-'} | {r.strategy_type} | "
                f"{r.total_score:.1f} | {_fmt_yen(close_val)} | {_fmt_yen(item.unit_capital)} | "
                f"{tv_str} | {_fmt_yen(item.gap_up_limit_price)} | {rs_str} | {_fmt_yen(item.poc_60d)} |"
            )
    lines.append("")
    return lines


def _render_stock_detail_block(
    item: GeminiStockBriefData,
    heading_prefix: str,
) -> List[str]:
    r = item.result
    lines: List[str] = [
        f"### {heading_prefix}{r.symbol} {r.company_name}（{r.sector or '-'} / {r.market or '-'}）",
        "",
    ]

    if item.data_missing:
        lines.append("- **状態**: OHLCV データが取得できないため詳細指標を算出できません。")
        lines.append("")
        return lines

    close_val = r.key_levels.get("close")
    pb_score = r.sub_scores.get("pullback_strategy_score")
    bo_score = r.sub_scores.get("breakout_strategy_score")
    te_score = r.sub_scores.get("trend_env_score")
    lines.append(
        f"- **スコア・戦略**: 総合 `{r.total_score:.1f}` / 戦略 `{r.strategy_type}` "
        f"（押し目 `{_fmt_num(pb_score, '.1f')}` / ブレイク `{_fmt_num(bo_score, '.1f')}` / "
        f"トレンド環境 `{_fmt_num(te_score, '.1f')}`）"
    )
    lines.append(
        f"- **資金・流動性・リスク**: 終値 `{_fmt_yen(close_val)}` | 1単元 `{_fmt_yen(item.unit_capital)}` | "
        f"20日平均売買代金 `{_fmt_num(item.avg_trading_value_20d_oku, '.1f', '億円')}` | "
        f"+3%見送り上限 `{_fmt_yen(item.gap_up_limit_price)}` | "
        f"ATR14 `{_fmt_yen(item.atr14)}` ({_fmt_pct(item.atr14_pct, signed=False)}) | "
        f"出来高倍率 `{_fmt_num(item.volume_ratio, '.2f', 'x')}`"
    )

    # 相対評価・財務詳細
    fin = item.financial_detail
    fcf_oku = (
        float(fin["free_cash_flow"]) / 100_000_000.0
        if fin.get("free_cash_flow") is not None
        else None
    )
    lines.append(
        f"- **相対評価・財務**: 対TOPIX RS順位 `{_fmt_num(item.rs_percentile, '.1f')}` | "
        f"業種モメンタム `{_fmt_num(item.sector_momentum_score, '.1f')}` | "
        f"業種内相対バリュエーションZ `{_fmt_num(item.relative_valuation_z, '+.2f')}` | "
        f"PER `{_fmt_num(fin.get('per'), '.1f', '倍')}` / PBR `{_fmt_num(fin.get('pbr'), '.2f', '倍')}` / "
        f"ROE `{_fmt_num(fin.get('roe'), '.1f', '%')}`"
    )
    inc_years = fin.get("consecutive_dividend_increase_years")
    inc_years_str = f"{inc_years}年" if inc_years is not None else "N/A"
    lines.append(
        f"- **成長・キャッシュ・株主還元**: 売上成長 `{_fmt_num(fin.get('revenue_growth'), '+.1f', '%')}` / "
        f"純利益成長 `{_fmt_num(fin.get('net_profit_growth'), '+.1f', '%')}` / "
        f"FCF `{_fmt_num(fcf_oku, '+,.1f', '億円')}` / "
        f"営業CFマージン `{_fmt_num(fin.get('operating_cf_margin'), '.1f', '%')}` / "
        f"総還元性向 `{_fmt_num(fin.get('total_payout_ratio'), '.1f', '%')}` / "
        f"連続増配 `{inc_years_str}`"
    )

    # 多層レジサポ＆MA傾き
    lines.append("")
    lines.append("#### 多層サポート・レジスタンス＆MA傾き")
    lines.append("| 指標 | 価格 | 終値からの乖離率 | 5日傾き | 向き |")
    lines.append("|---|---:|---:|---:|---|")
    for ma in item.ma_metrics:
        lines.append(
            f"| SMA{ma.period} | {_fmt_yen(ma.value)} | {_fmt_pct(ma.deviation_pct)} | "
            f"{_fmt_pct(ma.slope_5d_pct)} | {ma.slope_label} |"
        )
    lines.append(
        f"- **期間高安**: 20日 `{_fmt_yen(item.low_20d)} 〜 {_fmt_yen(item.high_20d)}` | "
        f"60日 `{_fmt_yen(item.low_60d)} 〜 {_fmt_yen(item.high_60d)}` | "
        f"250日 `{_fmt_yen(item.low_250d)} 〜 {_fmt_yen(item.high_250d)}`"
    )
    sh_date = item.swing_high_date.isoformat() if item.swing_high_date else "N/A"
    sl_date = item.swing_low_date.isoformat() if item.swing_low_date else "N/A"
    lines.append(
        f"- **構造節目**: 直近戻り高値 `{_fmt_yen(item.swing_high)}` ({sh_date}) | "
        f"直近押し安値 `{_fmt_yen(item.swing_low)}` ({sl_date}) | "
        f"直近60日POC `{_fmt_yen(item.poc_60d)}`"
    )

    if r.reasons:
        lines.append(f"- **判定根拠**: {' / '.join(r.reasons)}")

    # 直近15営業日 OHLCV
    if item.recent_ohlcv:
        lines.append("")
        lines.append("#### 直近15営業日 OHLCV")
        lines.append("| 日付 | 始値 | 高値 | 安値 | 終値 | 前日比 | 出来高倍率 |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for row in item.recent_ohlcv:
            lines.append(
                f"| {row.date.isoformat()} | {row.open:,.0f} | {row.high:,.0f} | "
                f"{row.low:,.0f} | {row.close:,.0f} | {_fmt_pct(row.change_pct)} | "
                f"{_fmt_num(row.volume_ratio, '.2f', 'x')} |"
            )

    lines.append("")
    return lines


def render_gemini_brief_markdown(
    candidate_items: Sequence[GeminiStockBriefData],
    watch_items: Sequence[GeminiStockBriefData],
    as_of_date: date,
    market_context: Optional[MarketContextModel] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Gemini 連携用の高密度 Markdown ブリーフ文字列を生成する（純粋生成処理）。
    """
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = [
        f"# Project Atlas Gemini 連携ブリーフ ({as_of_date.isoformat()})",
        "",
        f"- **基準日 (`as_of_date`)**: {as_of_date.isoformat()}",
        f"- **生成日時**: {generated_at}",
        f"- **1次スクリーニング抽出候補**: {len(candidate_items)} 件",
        f"- **既存監視銘柄（継続評価対象）**: {len(watch_items)} 件",
    ]
    if metadata:
        lines.append(
            f"- **対象処理銘柄数**: {metadata.get('processed_symbols_count', 'N/A')} / "
            f"通過件数: {metadata.get('filtered_count', 'N/A')}"
        )
    lines.append("")

    # 1. 市場環境・33業種ローテーション
    lines.extend(_render_market_section(market_context))

    # 2. 既存監視銘柄（継続評価対象）
    lines.append("## 2. 既存監視銘柄（継続評価対象・A〜D判定用）")
    lines.append("")
    if watch_items:
        lines.extend(_render_stock_summary_table(watch_items, include_rank=False))
        for item in watch_items:
            lines.extend(_render_stock_detail_block(item, heading_prefix="[監視] "))
    else:
        lines.append("- 指定された既存監視銘柄はありません。")
        lines.append("")

    # 3. 1次スクリーニング上位抽出候補
    lines.append("## 3. 1次スクリーニング上位抽出候補")
    lines.append("")
    if candidate_items:
        lines.extend(_render_stock_summary_table(candidate_items, include_rank=True))
        for item in candidate_items:
            lines.extend(
                _render_stock_detail_block(
                    item, heading_prefix=f"#{item.result.rank} "
                )
            )
    else:
        lines.append("- 本日の1次スクリーニング条件に合致する抽出候補はありませんでした。")
        lines.append("")

    return "\n".join(lines)


def export_gemini_brief(
    markdown_content: str,
    output_dir: Union[str, Path] = "./output",
    as_of_date: Optional[date] = None,
    prefix: str = "gemini_brief",
    latest_name: str = "gemini_brief_latest.md",
    deliveries: Optional[Iterable[BriefDeliveryBackend]] = None,
    fail_on_delivery_error: bool = False,
) -> Dict[str, DeliveryTarget]:
    """
    生成済みブリーフ Markdown をローカル output_dir へ書き出し（日付付き + latest 固定名）、
    必要に応じて外部配信バックエンド（ローカル同期フォルダ / Google Drive API 等）へ配信する。
    """
    resolved_date = as_of_date or date.today()
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dated_path = out_dir / f"{prefix}_{resolved_date.isoformat()}.md"
    latest_path = out_dir / latest_name

    dated_path.write_text(markdown_content, encoding="utf-8")
    latest_path.write_text(markdown_content, encoding="utf-8")

    exported: Dict[str, DeliveryTarget] = {
        "gemini": dated_path,
        "gemini_latest": latest_path,
    }

    delivery_errors: List[Exception] = []
    if deliveries:
        source_files = {"gemini": dated_path, "gemini_latest": latest_path}
        for backend in deliveries:
            try:
                delivered = backend.deliver(source_files, resolved_date)
                suffix = str(getattr(backend, "key_suffix", "copy") or "copy").strip()
                for key, dst_target in delivered.items():
                    base_key = f"{key}_{suffix}"
                    export_key = base_key
                    if export_key in exported:
                        seq = 2
                        while f"{base_key}_{seq}" in exported:
                            seq += 1
                        export_key = f"{base_key}_{seq}"
                    exported[export_key] = dst_target
            except Exception as e:
                delivery_errors.append(e)
                logger.warning(
                    f"ブリーフ配信バックエンドの実行に失敗しました（ローカル出力は成功しています）: {e}"
                )

    if fail_on_delivery_error and delivery_errors:
        raise delivery_errors[0]

    return exported
