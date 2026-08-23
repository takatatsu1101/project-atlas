
from typing import List, Optional, Dict
from datetime import date

from src.model.data_models import OhlcvModel, IndicatorSetModel, FinancialModel, FeatureSetModel, FeatureResultModel
from src.feature_engine.registry import feature_registry
from src.feature_engine.interfaces import IFeature

class FeatureManager:
    def __init__(self):
        self.registry = feature_registry

    def calculate_features(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None,
        feature_ids: Optional[List[str]] = None
    ) -> List[FeatureSetModel]:
        """
        指定された入力データに基づいて特徴量を計算し、結果のリストを返す。
        feature_idsが指定された場合は、その特徴量のみを計算する。
        """
        if not ohlcv_data or not indicator_data:
            print("警告: OHLCVデータまたは指標データが不足しているため、特徴量を計算できません。")
            return []

        all_feature_sets: Dict[date, List[FeatureResultModel]] = {}

        # 登録されている全特徴量、または指定された特徴量のみを処理
        features_to_calculate: List[IFeature] = []
        if feature_ids:
            for f_id in feature_ids:
                features_to_calculate.append(self.registry.get_feature(f_id))
        else:
            # 全ての特徴量を取得 (registry.pyのlist_featuresをIFeatureインスタンスで返すように修正が必要かも)
            # 登録されている全ての特徴量を取得して追加
            for feature_info in self.registry.list_features():
                features_to_calculate.append(self.registry.get_feature(feature_info["feature_id"]))

        for feature_instance in features_to_calculate:
            print(f"特徴量 {feature_instance.feature_name} を計算中...")
            feature_results = feature_instance.calculate(ohlcv_data, indicator_data, financial_data)
            for result in feature_results:
                if result.date not in all_feature_sets:
                    all_feature_sets[result.date] = []
                all_feature_sets[result.date].append(result)
        
        # 日付ごとにFeatureSetModelを作成
        final_feature_sets: List[FeatureSetModel] = []
        for date_key in sorted(all_feature_sets.keys()):
            final_feature_sets.append(FeatureSetModel(
                symbol=ohlcv_data[0].symbol, # 全てのOHLCVデータが同じsymbolを持つと仮定
                date=date_key,
                results=all_feature_sets[date_key]
            ))

        print(f"{ohlcv_data[0].symbol} の特徴量計算が完了しました。")
        return final_feature_sets

# モジュールレベルでインスタンス化
feature_manager = FeatureManager()

def calculate_features(
    ohlcv_data: List[OhlcvModel],
    indicator_data: List[IndicatorSetModel],
    financial_data: Optional[FinancialModel] = None,
    feature_ids: Optional[List[str]] = None
) -> List[FeatureSetModel]:
    return feature_manager.calculate_features(ohlcv_data, indicator_data, financial_data, feature_ids)
