
from typing import Dict, Type, List
from src.feature_engine.interfaces import IFeature

class FeatureRegistry:
    def __init__(self):
        self._features: Dict[str, Type[IFeature]] = {}

    def register(self, feature_class: Type[IFeature]):
        """
        IFeatureを実装する特徴量クラスを登録する。
        """
        if not issubclass(feature_class, IFeature):
            raise ValueError("登録できるのはIFeatureを実装したクラスのみです。")
        self._features[feature_class.feature_id] = feature_class
        print(f"Feature \'{feature_class.feature_name}\' ({feature_class.feature_id}) を登録しました。")

    def get_feature(self, feature_id: str) -> IFeature:
        """
        指定されたIDの特徴量インスタンスを返す。
        """
        feature_class = self._features.get(feature_id)
        if not feature_class:
            raise ValueError(f"Feature ID \'{feature_id}\' が見つかりません。")
        return feature_class() # インスタンスを生成して返す

    def list_features(self) -> List[Dict[str, str]]:
        """
        登録されている全ての特徴量のリストを返す。
        """
        return [{
            "feature_id": f_id,
            "feature_name": f_class.feature_name,
            "feature_category": f_class.feature_category
        } for f_id, f_class in self._features.items()]

# シングルトンインスタンス
feature_registry = FeatureRegistry()
