import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from src.common.logger import get_logger
from src.model.data_models import AnalysisResultModel

logger = get_logger(__name__)

STRATEGY_LABELS: Dict[str, str] = {
    "pullback": "押し目買い型",
    "breakout": "ブレイクアウト型",
    "watch": "監視",
}

_SUB_SCORE_LABELS: Dict[str, str] = {
    "pullback_strategy_score": "押し目戦略スコア",
    "breakout_strategy_score": "ブレイク戦略スコア",
    "trend_env_score": "トレンド環境スコア",
    "fundamental_score": "ファンダメンタルスコア",
    "penalty_score": "ペナルティ減点",
}


class Presenter:
    """分析結果のCLI表示および構造化レポート（JSON / Markdown）出力を担当するクラス"""

    @staticmethod
    def _strategy_label(strategy_type: str) -> str:
        return STRATEGY_LABELS.get(strategy_type, strategy_type)

    @staticmethod
    def _normalize_date(value: Any) -> Optional[date]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        return value

    @classmethod
    def _resolve_as_of_date(
        cls,
        analysis_results: Sequence[AnalysisResultModel],
        as_of_date: Optional[date] = None,
    ) -> date:
        if as_of_date is not None:
            return cls._normalize_date(as_of_date) or date.today()
        for res in analysis_results:
            if res.date is not None:
                norm = cls._normalize_date(res.date)
                if norm is not None:
                    return norm
        return date.today()

    @staticmethod
    def _fmt_num(
        value: Optional[float], decimals: int = 2, suffix: str = ""
    ) -> str:
        if value is None:
            return "-"
        return f"{value:,.{decimals}f}{suffix}"

    @staticmethod
    def _fmt_pct(value: Optional[float], signed: bool = False) -> str:
        if value is None:
            return "-"
        if signed:
            return f"{value:+.2f}%"
        return f"{value:.2f}%"

    @staticmethod
    def _fmt_amount(value: Optional[float]) -> str:
        if value is None:
            return "-"
        if abs(value) >= 100_000_000:
            return f"{value / 100_000_000:,.1f}億円"
        return f"{value:,.0f}円"

    def _serialize_candidate(self, result: AnalysisResultModel) -> Dict[str, Any]:
        norm_date = self._normalize_date(result.date)
        return {
            "rank": result.rank,
            "symbol": result.symbol,
            "company_name": result.company_name,
            "market": result.market,
            "sector": result.sector,
            "date": norm_date.isoformat() if norm_date is not None else None,
            "strategy_type": result.strategy_type,
            "strategy_label": self._strategy_label(result.strategy_type),
            "total_score": result.total_score,
            "sub_scores": dict(result.sub_scores or {}),
            "key_levels": dict(result.key_levels or {}),
            "risk_metrics": dict(result.risk_metrics or {}),
            "financial_summary": dict(result.financial_summary or {}),
            "reasons": list(result.reasons or []),
            "feature_results": [
                {
                    "feature_id": fr.feature_id,
                    "feature_name": fr.feature_name,
                    "score": fr.score,
                    "raw_value": fr.raw_value,
                    "date": (
                        self._normalize_date(fr.date).isoformat()
                        if fr.date is not None
                        else None
                    ),
                    "metadata": dict(fr.metadata or {}),
                }
                for fr in (result.feature_results or [])
            ],
            "pattern_results": [
                {
                    "pattern_id": pr.pattern_id,
                    "pattern_name": pr.pattern_name,
                    "confidence": pr.confidence,
                    "metadata": dict(pr.metadata or {}),
                }
                for pr in (result.pattern_results or [])
            ],
            "summary": result.summary,
        }

    def _resolve_strategy_rankings(
        self,
        analysis_results: Sequence[AnalysisResultModel],
        strategy_rankings: Optional[Dict[str, List[AnalysisResultModel]]],
    ) -> Dict[str, List[AnalysisResultModel]]:
        """
        strategy_rankings が未指定の場合、analysis_results から戦略別に再ソート・連番順位付けした
        フォールバック辞書を生成する（元の AnalysisResultModel は変更しない）。
        """
        if strategy_rankings is not None:
            return dict(strategy_rankings)

        def _build_sub_ranking(strategy_key: str, score_key: str) -> List[AnalysisResultModel]:
            matched = [r for r in analysis_results if r.strategy_type == strategy_key]
            sorted_items = sorted(
                matched,
                key=lambda x: (
                    -float((x.sub_scores or {}).get(score_key, x.total_score)),
                    -float((x.sub_scores or {}).get("trend_env_score", 0.0)),
                    x.symbol,
                ),
            )
            return [
                item.model_copy(update={"rank": idx})
                for idx, item in enumerate(sorted_items, start=1)
            ]

        return {
            "overall": list(analysis_results),
            "pullback": _build_sub_ranking("pullback", "pullback_strategy_score"),
            "breakout": _build_sub_ranking("breakout", "breakout_strategy_score"),
        }

    def _build_strategy_rankings_payload(
        self,
        analysis_results: Sequence[AnalysisResultModel],
        strategy_rankings: Optional[Dict[str, List[AnalysisResultModel]]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        resolved = self._resolve_strategy_rankings(analysis_results, strategy_rankings)
        return {
            key: [self._serialize_candidate(item) for item in items]
            for key, items in resolved.items()
        }

    @staticmethod
    def _build_summary_stats(
        analysis_results: Sequence[AnalysisResultModel],
    ) -> Dict[str, Any]:
        counts: Dict[str, int] = {"pullback": 0, "breakout": 0, "watch": 0}
        for res in analysis_results:
            counts[res.strategy_type] = counts.get(res.strategy_type, 0) + 1
        top_item = analysis_results[0] if analysis_results else None
        return {
            "total_candidates": len(analysis_results),
            "strategy_counts": counts,
            "top_symbol": top_item.symbol if top_item else None,
            "top_score": top_item.total_score if top_item else None,
        }

    def display_results(
        self,
        analysis_results: List[AnalysisResultModel],
        output_type: str = "cli",
        output_dir: Union[str, Path] = "./output",
        output_path: Optional[Union[str, Path]] = None,
        as_of_date: Optional[date] = None,
        strategy_rankings: Optional[Dict[str, List[AnalysisResultModel]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Path]]:
        """
        分析結果をCLIまたは構造化レポート（json / markdown / all）で出力する。
        """
        norm_type = (output_type or "cli").lower()

        if norm_type == "cli":
            if not analysis_results:
                print("表示する分析結果がありません。")
                return None
            self._display_cli(analysis_results)
            return None

        if norm_type == "json":
            path = self.export_json(
                analysis_results,
                output_path=output_path,
                output_dir=output_dir,
                as_of_date=as_of_date,
                strategy_rankings=strategy_rankings,
                metadata=metadata,
            )
            return {"json": path}

        if norm_type in ("markdown", "md"):
            path = self.export_markdown(
                analysis_results,
                output_path=output_path,
                output_dir=output_dir,
                as_of_date=as_of_date,
                strategy_rankings=strategy_rankings,
                metadata=metadata,
            )
            return {"markdown": path}

        if norm_type == "all":
            if not analysis_results:
                print("表示する分析結果がありません。")
            else:
                self._display_cli(analysis_results)
            return self.export_reports(
                analysis_results,
                output_dir=output_dir,
                formats=("json", "markdown"),
                as_of_date=as_of_date,
                strategy_rankings=strategy_rankings,
                metadata=metadata,
            )

        if norm_type == "gui":
            print("GUI表示は未実装です。CLIで表示します。")
        else:
            print(f"不明な出力タイプ: {output_type}。CLIで表示します。")

        if not analysis_results:
            print("表示する分析結果がありません。")
            return None
        self._display_cli(analysis_results)
        return None

    def _display_cli(self, analysis_results: List[AnalysisResultModel]) -> None:
        """
        CLI形式で結果を視認性よく出力する。
        """
        print("\n=== Project Atlas 分析結果 ===")
        for result in analysis_results:
            rank_str = f"{result.rank}位" if result.rank is not None else "-"
            strategy_label = self._strategy_label(result.strategy_type)
            norm_date = self._normalize_date(result.date)
            date_str = norm_date.isoformat() if norm_date is not None else "-"
            market_sector = " / ".join(
                part for part in (result.market, result.sector) if part
            ) or "-"

            print(
                f"\n[{rank_str}] {result.symbol} {result.company_name} "
                f"| 戦略: {strategy_label} ({result.strategy_type}) "
                f"| 総合スコア: {result.total_score:.2f}"
            )
            print(f"  基準日: {date_str} | 市場・業種: {market_sector}")
            if result.summary:
                print(f"  サマリー: {result.summary}")

            if result.sub_scores:
                sub_parts = [
                    f"{_SUB_SCORE_LABELS.get(k, k)}: {v:.1f}"
                    for k, v in result.sub_scores.items()
                ]
                print(f"  サブスコア: {' / '.join(sub_parts)}")

            kl = result.key_levels or {}
            if kl:
                print(
                    "  価格水準: "
                    f"現在値={self._fmt_num(kl.get('close'))}, "
                    f"SMA5={self._fmt_num(kl.get('sma5'))} ({self._fmt_pct(kl.get('sma5_deviation_pct'), signed=True)}), "
                    f"SMA25={self._fmt_num(kl.get('sma25'))} ({self._fmt_pct(kl.get('sma25_deviation_pct'), signed=True)}), "
                    f"SMA75={self._fmt_num(kl.get('sma75'))} ({self._fmt_pct(kl.get('sma75_deviation_pct'), signed=True)}), "
                    f"20日高値={self._fmt_num(kl.get('highest_high'))}, "
                    f"20日安値={self._fmt_num(kl.get('lowest_low'))}"
                )

            rm = result.risk_metrics or {}
            if rm:
                print(
                    "  リスク指標: "
                    f"ATR={self._fmt_num(rm.get('atr'))}, "
                    f"ATR%={self._fmt_pct(rm.get('atr_pct'))}, "
                    f"出来高倍率={self._fmt_num(rm.get('volume_ratio'), suffix='x')}, "
                    f"ボラ比={self._fmt_num(rm.get('volatility_ratio'))}"
                )

            fs = result.financial_summary or {}
            if fs:
                print(
                    "  財務指標: "
                    f"PER={self._fmt_num(fs.get('per'), suffix='倍')}, "
                    f"PBR={self._fmt_num(fs.get('pbr'), suffix='倍')}, "
                    f"ROE={self._fmt_pct(fs.get('roe'))}, "
                    f"売上成長率={self._fmt_pct(fs.get('revenue_growth'), signed=True)}, "
                    f"純利益成長率={self._fmt_pct(fs.get('net_profit_growth'), signed=True)}, "
                    f"自己資本比率={self._fmt_pct(fs.get('equity_ratio'))}"
                )

            if result.reasons:
                print("  --- 判定根拠 ---")
                for reason in result.reasons:
                    print(f"    * {reason}")

            if result.feature_results:
                print("  --- 特徴量 ---")
                for fr in result.feature_results:
                    print(
                        f"    - {fr.feature_name} ({fr.feature_id}): "
                        f"スコア {fr.score:.2f} (生値: {fr.raw_value:.2f})"
                    )

            if result.pattern_results:
                print("  --- 検出パターン ---")
                for pr in result.pattern_results:
                    print(
                        f"    - {pr.pattern_name} ({pr.pattern_id}): "
                        f"信頼度 {pr.confidence:.2f}"
                    )
        print("==============================")

    def export_json(
        self,
        analysis_results: List[AnalysisResultModel],
        output_path: Optional[Union[str, Path]] = None,
        output_dir: Union[str, Path] = "./output",
        as_of_date: Optional[date] = None,
        strategy_rankings: Optional[Dict[str, List[AnalysisResultModel]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        後段AI連携用の構造化JSONレポートを出力し、保存先 Path を返す。
        """
        resolved_date = self._resolve_as_of_date(analysis_results, as_of_date)
        if output_path is not None:
            target_path = Path(output_path)
        else:
            target_path = (
                Path(output_dir) / f"screening_report_{resolved_date.isoformat()}.json"
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of_date": resolved_date.isoformat(),
            "summary": self._build_summary_stats(analysis_results),
            "metadata": metadata or {},
            "candidates": [self._serialize_candidate(r) for r in analysis_results],
            "strategy_rankings": self._build_strategy_rankings_payload(
                analysis_results, strategy_rankings
            ),
        }

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"JSONレポートを出力しました: {target_path}")
        return target_path

    def export_markdown(
        self,
        analysis_results: List[AnalysisResultModel],
        output_path: Optional[Union[str, Path]] = None,
        output_dir: Union[str, Path] = "./output",
        as_of_date: Optional[date] = None,
        strategy_rankings: Optional[Dict[str, List[AnalysisResultModel]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        AI連携・人間閲覧用の構造化Markdownレポートを出力し、保存先 Path を返す。
        """
        resolved_date = self._resolve_as_of_date(analysis_results, as_of_date)
        if output_path is not None:
            target_path = Path(output_path)
        else:
            target_path = (
                Path(output_dir) / f"screening_report_{resolved_date.isoformat()}.md"
            )
        target_path.parent.mkdir(parents=True, exist_ok=True)

        stats = self._build_summary_stats(analysis_results)
        strategy_counts = stats["strategy_counts"]
        lines: List[str] = [
            f"# Project Atlas スクリーニングレポート ({resolved_date.isoformat()})",
            "",
            f"- 基準日: `{resolved_date.isoformat()}`",
            f"- 生成日時: `{datetime.now().isoformat(timespec='seconds')}`",
            f"- 抽出銘柄数: **{stats['total_candidates']} 件**",
            f"- 戦略別内訳: 押し目買い型 {strategy_counts.get('pullback', 0)} 件 / "
            f"ブレイクアウト型 {strategy_counts.get('breakout', 0)} 件 / "
            f"監視 {strategy_counts.get('watch', 0)} 件",
        ]
        if metadata:
            meta_items = ", ".join(f"{k}={v}" for k, v in metadata.items())
            lines.append(f"- 実行メタ情報: {meta_items}")
        lines.append("")

        # 全体サマリーテーブル
        lines.append("## 全体サマリー")
        lines.append("")
        if not analysis_results:
            lines.append("条件に合致する推奨銘柄はありませんでした。")
            lines.append("")
        else:
            lines.extend(
                [
                    "| 順位 | 銘柄コード | 銘柄名 | 市場 | 業種 | 戦略 | 総合スコア | トレンド環境 | 現在値 | PER | PBR | ROE |",
                    "|---:|:---|:---|:---|:---|:---|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for res in analysis_results:
                kl = res.key_levels or {}
                fs = res.financial_summary or {}
                sub = res.sub_scores or {}
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(res.rank if res.rank is not None else "-"),
                            res.symbol,
                            res.company_name or "-",
                            res.market or "-",
                            res.sector or "-",
                            self._strategy_label(res.strategy_type),
                            self._fmt_num(res.total_score),
                            self._fmt_num(sub.get("trend_env_score")),
                            self._fmt_num(kl.get("close")),
                            self._fmt_num(fs.get("per"), suffix="倍"),
                            self._fmt_num(fs.get("pbr"), suffix="倍"),
                            self._fmt_pct(fs.get("roe")),
                        ]
                    )
                    + " |"
                )
            lines.append("")

        # 戦略別ランキング
        lines.append("## 戦略別ランキング")
        lines.append("")
        resolved_rankings = self._resolve_strategy_rankings(
            analysis_results, strategy_rankings
        )
        pullback_list = resolved_rankings.get("pullback", [])
        breakout_list = resolved_rankings.get("breakout", [])

        for strat_key, strat_title, items in (
            ("pullback", "押し目買い型ランキング", pullback_list),
            ("breakout", "ブレイクアウト型ランキング", breakout_list),
        ):
            lines.append(f"### {strat_title}")
            lines.append("")
            if not items:
                lines.append("該当銘柄なし。")
                lines.append("")
                continue
            lines.extend(
                [
                    "| 順位 | 銘柄コード | 銘柄名 | 戦略スコア | 総合スコア | 現在値 | 主な根拠 |",
                    "|---:|:---|:---|---:|---:|---:|:---|",
                ]
            )
            score_key = (
                "pullback_strategy_score"
                if strat_key == "pullback"
                else "breakout_strategy_score"
            )
            for idx, item in enumerate(items, start=1):
                strat_score = (item.sub_scores or {}).get(score_key, item.total_score)
                top_reason = item.reasons[0] if item.reasons else "-"
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(item.rank if item.rank is not None else idx),
                            item.symbol,
                            item.company_name or "-",
                            self._fmt_num(strat_score),
                            self._fmt_num(item.total_score),
                            self._fmt_num((item.key_levels or {}).get("close")),
                            top_reason.replace("|", "\\|"),
                        ]
                    )
                    + " |"
                )
            lines.append("")

        # 各推奨銘柄の詳細セクション
        lines.append("## 推奨銘柄詳細")
        lines.append("")
        if not analysis_results:
            lines.append("詳細対象の銘柄はありません。")
            lines.append("")
        else:
            for res in analysis_results:
                rank_str = f"{res.rank}位" if res.rank is not None else "-"
                norm_date = self._normalize_date(res.date)
                date_str = norm_date.isoformat() if norm_date is not None else "-"
                strategy_label = self._strategy_label(res.strategy_type)

                lines.append(
                    f"### {rank_str}: {res.symbol} {res.company_name}（{strategy_label}）"
                )
                lines.append("")
                lines.append("#### 基本情報")
                lines.append(
                    f"- 市場 / 業種: {res.market or '-'} / {res.sector or '-'}"
                )
                lines.append(f"- 基準日: `{date_str}`")
                lines.append(
                    f"- 戦略タイプ: **{strategy_label}** (`{res.strategy_type}`)"
                )
                lines.append(f"- 総合スコア: **{res.total_score:.2f}**")
                if res.sub_scores:
                    sub_str = ", ".join(
                        f"{_SUB_SCORE_LABELS.get(k, k)}: {v:.2f}"
                        for k, v in res.sub_scores.items()
                    )
                    lines.append(f"- サブスコア内訳: {sub_str}")
                if res.summary:
                    lines.append(f"- サマリー: {res.summary}")
                lines.append("")

                # 価格水準＆サポレジテーブル
                kl = res.key_levels or {}
                lines.append("#### 価格水準・サポート/レジスタンス")
                lines.extend(
                    [
                        "| 指標 | 水準 | 乖離率 |",
                        "|:---|---:|---:|",
                        f"| 現在値 (Close) | {self._fmt_num(kl.get('close'))} | - |",
                        f"| SMA5 | {self._fmt_num(kl.get('sma5'))} | {self._fmt_pct(kl.get('sma5_deviation_pct'), signed=True)} |",
                        f"| SMA25 | {self._fmt_num(kl.get('sma25'))} | {self._fmt_pct(kl.get('sma25_deviation_pct'), signed=True)} |",
                        f"| SMA75 | {self._fmt_num(kl.get('sma75'))} | {self._fmt_pct(kl.get('sma75_deviation_pct'), signed=True)} |",
                        f"| 直近20日高値 (レジスタンス) | {self._fmt_num(kl.get('highest_high'))} | - |",
                        f"| 直近20日安値 (サポート) | {self._fmt_num(kl.get('lowest_low'))} | - |",
                        "",
                    ]
                )

                # リスク指標
                rm = res.risk_metrics or {}
                lines.append("#### リスク指標")
                lines.append(f"- ATR(14): {self._fmt_num(rm.get('atr'))}")
                lines.append(f"- ATR%: {self._fmt_pct(rm.get('atr_pct'))}")
                lines.append(
                    f"- ボラティリティ比率: {self._fmt_num(rm.get('volatility_ratio'))}"
                )
                lines.append(
                    f"- 出来高倍率: {self._fmt_num(rm.get('volume_ratio'), suffix='倍')}"
                )
                lines.append("")

                # 主要財務指標
                fs = res.financial_summary or {}
                lines.append("#### 主要財務指標")
                if not fs:
                    lines.append("- 財務データなし")
                else:
                    lines.extend(
                        [
                            "| 指標 | 値 | 指標 | 値 |",
                            "|:---|---:|:---|---:|",
                            f"| PER | {self._fmt_num(fs.get('per'), suffix='倍')} | PBR | {self._fmt_num(fs.get('pbr'), suffix='倍')} |",
                            f"| ROE | {self._fmt_pct(fs.get('roe'))} | ROA | {self._fmt_pct(fs.get('roa'))} |",
                            f"| 売上高成長率(単年) | {self._fmt_pct(fs.get('revenue_growth'), signed=True)} | 純利益成長率(単年) | {self._fmt_pct(fs.get('net_profit_growth'), signed=True)} |",
                            f"| 売上高成長率(3年CAGR) | {self._fmt_pct(fs.get('revenue_growth_3y_avg'), signed=True)} | 純利益成長率(3年CAGR) | {self._fmt_pct(fs.get('net_profit_growth_3y_avg'), signed=True)} |",
                            f"| 自己資本比率 | {self._fmt_pct(fs.get('equity_ratio'))} | EPS / BPS | {self._fmt_num(fs.get('eps'))} / {self._fmt_num(fs.get('bps'))} |",
                            f"| 売上高 | {self._fmt_amount(fs.get('revenue'))} | 営業利益 / 純利益 | {self._fmt_amount(fs.get('operating_profit'))} / {self._fmt_amount(fs.get('net_profit'))} |",
                        ]
                    )
                lines.append("")

                # 判定根拠
                lines.append("#### 判定根拠")
                if res.reasons:
                    for reason in res.reasons:
                        lines.append(f"- {reason}")
                else:
                    lines.append("- 特記事項なし")
                lines.append("")

                # 検出パターン・主要特徴量
                lines.append("#### 検出パターン・主要特徴量")
                if res.pattern_results:
                    lines.append("- **検出パターン**:")
                    for pr in res.pattern_results:
                        lines.append(
                            f"  - {pr.pattern_name} (`{pr.pattern_id}`): 信頼度 {pr.confidence:.2f}"
                        )
                else:
                    lines.append("- **検出パターン**: なし")

                if res.feature_results:
                    lines.append("- **主要特徴量**:")
                    for fr in res.feature_results:
                        lines.append(
                            f"  - {fr.feature_name} (`{fr.feature_id}`): "
                            f"スコア {fr.score:.2f} (生値: {fr.raw_value:.2f})"
                        )
                else:
                    lines.append("- **主要特徴量**: なし")
                lines.append("")

        target_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Markdownレポートを出力しました: {target_path}")
        return target_path

    def export_reports(
        self,
        analysis_results: List[AnalysisResultModel],
        output_dir: Union[str, Path] = "./output",
        formats: Iterable[str] = ("json", "markdown"),
        as_of_date: Optional[date] = None,
        strategy_rankings: Optional[Dict[str, List[AnalysisResultModel]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Path]:
        """
        指定された複数フォーマット（json, markdown）のレポートをまとめて出力する。
        """
        exported: Dict[str, Path] = {}
        for fmt in formats:
            norm_fmt = str(fmt).strip().lower()
            if norm_fmt == "json":
                exported["json"] = self.export_json(
                    analysis_results,
                    output_dir=output_dir,
                    as_of_date=as_of_date,
                    strategy_rankings=strategy_rankings,
                    metadata=metadata,
                )
            elif norm_fmt in ("markdown", "md"):
                exported["markdown"] = self.export_markdown(
                    analysis_results,
                    output_dir=output_dir,
                    as_of_date=as_of_date,
                    strategy_rankings=strategy_rankings,
                    metadata=metadata,
                )
            else:
                logger.warning(f"未対応のレポートフォーマットが指定されました: {fmt}")
        return exported


# モジュールレベルでインスタンス化
presenter = Presenter()


def display_results(
    analysis_results: List[AnalysisResultModel],
    output_type: str = "cli",
    output_dir: Union[str, Path] = "./output",
    output_path: Optional[Union[str, Path]] = None,
    as_of_date: Optional[date] = None,
    strategy_rankings: Optional[Dict[str, List[AnalysisResultModel]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Path]]:
    return presenter.display_results(
        analysis_results,
        output_type=output_type,
        output_dir=output_dir,
        output_path=output_path,
        as_of_date=as_of_date,
        strategy_rankings=strategy_rankings,
        metadata=metadata,
    )
