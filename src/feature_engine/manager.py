
from typing import List, Optional, Dict
from datetime import date

from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureSetModel, FeatureResultModel
from src.feature_engine.registry import feature_registry
from src.feature_engine.interfaces import IFeature
from src.common.storage import StorageManager
from src.common.logger import get_logger

logger = get_logger("FeatureManager")

class FeatureManager:
    def __init__(self):
        self.registry = feature_registry
        self.storage = StorageManager()

    def calculate_features(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None,
        feature_ids: Optional[List[str]] = None,
        use_cache: bool = True,
        cache_key_suffix: Optional[str] = None,
    ) -> List[FeatureSetModel]:
        """
        指定された入力データに基づいて特徴量を計算し、結果のリストを返す（キャッシュ対応）。
        feature_idsが指定された場合は、その特徴量のみを計算する。
        use_cache=False の場合はキャッシュの読み込み・保存をスキップする。
        cache_key_suffix を指定した場合はサフィックス付きのキャッシュキーを使用する。
        """
        if not ohlcv_data or not indicator_data:
            logger.warning("OHLCVデータまたは指標データが不足しているため、特徴量を計算できません。")
            return []

        symbol = ohlcv_data[0].symbol
        f_suffix = "_".join(sorted(feature_ids)) if feature_ids else "all"
        cache_path = (
            f"cache/features_{symbol}_{f_suffix}_{cache_key_suffix}.json"
            if cache_key_suffix
            else f"cache/features_{symbol}_{f_suffix}.json"
        )
        expected_dates = [o.date.isoformat()[:10] for o in ohlcv_data]
        expected_fin_sig = (
            financial_data.model_dump(mode="json")
            if financial_data is not None
            else None
        )

        # キャッシュチェック（meta.dates と meta.financial_signature の完全一致を検証、旧形式リストは無視）
        if use_cache:
            cached_data = self.storage.load_json(cache_path)
            if isinstance(cached_data, dict):
                meta = cached_data.get("meta")
                items = cached_data.get("items")
                if (
                    isinstance(meta, dict)
                    and meta.get("dates") == expected_dates
                    and meta.get("financial_signature") == expected_fin_sig
                    and isinstance(items, list)
                ):
                    logger.info(f"{symbol} の特徴量をキャッシュからロードしました。")
                    return [FeatureSetModel(**item) for item in items]

        all_feature_sets: Dict[date, List[FeatureResultModel]] = {}

        # 登録されている全特徴量、または指定された特徴量のみを処理
        features_to_calculate: List[IFeature] = []
        if feature_ids:
            for f_id in feature_ids:
                features_to_calculate.append(self.registry.get_feature(f_id))
        else:
            for feature_info in self.registry.list_features():
                features_to_calculate.append(self.registry.get_feature(feature_info["feature_id"]))

        for feature_instance in features_to_calculate:
            logger.info(f"特徴量 {feature_instance.feature_name} を計算中...")
            feature_results = feature_instance.calculate(ohlcv_data, indicator_data, financial_data)
            for result in feature_results:
                if result.date not in all_feature_sets:
                    all_feature_sets[result.date] = []
                all_feature_sets[result.date].append(result)
        
        # 日付ごとにFeatureSetModelを作成
        final_feature_sets: List[FeatureSetModel] = []
        for date_key in sorted(all_feature_sets.keys()):
            final_feature_sets.append(FeatureSetModel(
                symbol=symbol,
                date=date_key,
                results=all_feature_sets[date_key]
            ))

        # キャッシュとして保存
        if use_cache:
            try:
                cache_payload = {
                    "meta": {
                        "dates": expected_dates,
                        "financial_signature": expected_fin_sig,
                    },
                    "items": [model.model_dump(mode="json") for model in final_feature_sets],
                }
                self.storage.save_json(cache_payload, cache_path)
            except Exception as e:
                logger.warning(f"特徴量キャッシュの保存に失敗しました: {e}")

            logger.info(f"{symbol} の特徴量計算・キャッシュが完了しました。")
        else:
            logger.info(f"{symbol} の特徴量計算が完了しました（キャッシュ無効）。")
        return final_feature_sets

# モジュールレベルでインスタンス化
feature_manager = FeatureManager()

def calculate_features(
    ohlcv_data: List[OhlcvModel],
    indicator_data: List[IndicatorSetModel],
    financial_data: Optional[FinancialModel] = None,
    feature_ids: Optional[List[str]] = None,
    use_cache: bool = True,
    cache_key_suffix: Optional[str] = None,
) -> List[FeatureSetModel]:
    return feature_manager.calculate_features(
        ohlcv_data,
        indicator_data,
        financial_data,
        feature_ids,
        use_cache=use_cache,
        cache_key_suffix=cache_key_suffix,
    )
