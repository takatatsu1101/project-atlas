class AtlasError(Exception):
    """
    ProjectAtlasのベースカスタム例外クラス。
    """
    pass

class DataCollectionError(AtlasError):
    """
    データ収集時に発生する例外。
    """
    pass

class IndicatorCalculationError(AtlasError):
    """
    指標計算時に発生する例外。
    """
    pass

class FeatureCalculationError(AtlasError):
    """
    特徴量計算時に発生する例外。
    """
    pass

class PatternDetectionError(AtlasError):
    """
    パターン検出時に発生する例外。
    """
    pass

class ScoreCalculationError(AtlasError):
    """
    スコア計算時に発生する例外。
    """
    pass
