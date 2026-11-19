import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.common.indexing import resolve_target_indices
from src.feature_engine.features.utils import (
    linear_scale,
    normalize_score_range,
    to_finite_float,
)
from src.feature_engine.interfaces import IFeature
from src.feature_engine.registry import feature_registry
from src.model.data_models import (
    FeatureResultModel,
    FinancialModel,
    IndicatorSetModel,
    OhlcvModel,
)


class EarningsQualityScore(IFeature):
    """利益の質スコア（営業CF裏付け・FCF・営業CFマージン・実効税率整合性・レバレッジ健全性）"""

    feature_id: str = "F005_EarningsQualityScore"
    feature_name: str = "利益の質スコア"
    feature_category: str = "Fundamental"

    def calculate(
        self,
        ohlcv_data: List[OhlcvModel],
        indicator_data: List[IndicatorSetModel],
        financial_data: Optional[FinancialModel] = None,
        target_indices: Optional[Sequence[int]] = None,
    ) -> List[FeatureResultModel]:
        """対象インデックスに対して利益の質スコアを算出する。"""
        if not indicator_data:
            return []

        raw_score, metadata = self._evaluate_financials(financial_data)
        normalized_score = self._normalize_score(raw_score, 0.0, 100.0)

        results: List[FeatureResultModel] = []
        for i in resolve_target_indices(len(indicator_data), target_indices):
            ind_set = indicator_data[i]
            results.append(
                FeatureResultModel(
                    feature_id=self.feature_id,
                    feature_name=self.feature_name,
                    score=normalized_score,
                    raw_value=raw_score,
                    metadata=dict(metadata),
                    date=ind_set.date,
                )
            )
        return results

    def _evaluate_financials(
        self, financial_data: Optional[FinancialModel]
    ) -> Tuple[float, Dict[str, Any]]:
        """財務諸表・CFデータから生スコア（0〜100）とメタデータを算出する。"""
        if financial_data is None:
            return 50.0, {}

        operating_cf = to_finite_float(financial_data.operating_cf)
        free_cash_flow = to_finite_float(financial_data.free_cash_flow)
        capex = to_finite_float(financial_data.capex)
        operating_cf_margin = to_finite_float(financial_data.operating_cf_margin)
        total_assets = to_finite_float(financial_data.total_assets)
        revenue = to_finite_float(financial_data.revenue)
        operating_profit = to_finite_float(financial_data.operating_profit)
        ordinary_profit = to_finite_float(financial_data.ordinary_profit)
        net_profit = to_finite_float(financial_data.net_profit)
        roe = to_finite_float(financial_data.roe)
        roa = to_finite_float(financial_data.roa)

        # FCF フォールバック（free_cash_flow 無し時は operating_cf - abs(capex)）
        fcf = free_cash_flow
        if fcf is None and operating_cf is not None and capex is not None:
            fcf_candidate = operating_cf - abs(capex)
            if math.isfinite(fcf_candidate):
                fcf = fcf_candidate

        # 営業CFマージン フォールバック（%）
        ocf_margin = operating_cf_margin
        if ocf_margin is None and operating_cf is not None and revenue is not None and revenue > 0.0:
            margin_candidate = (operating_cf / revenue) * 100.0
            if math.isfinite(margin_candidate):
                ocf_margin = margin_candidate

        weighted_sum = 0.0
        weight_sum = 0.0

        # 1. アクルーアルズ / 営業CF裏付け（ウェイト 35.0）
        cf_to_net_profit, acc_score = self._calc_accruals_score(operating_cf, net_profit)
        if acc_score is not None:
            weighted_sum += acc_score
            weight_sum += 35.0

        # 2. フリーCF（ウェイト 25.0）
        fcf_to_assets, fcf_score = self._calc_fcf_score(fcf, total_assets, revenue)
        if fcf_score is not None:
            weighted_sum += fcf_score
            weight_sum += 25.0

        # 3. 営業CFマージン（ウェイト 15.0）
        ocf_margin_score = self._calc_ocf_margin_score(ocf_margin)
        if ocf_margin_score is not None:
            weighted_sum += ocf_margin_score
            weight_sum += 15.0

        # 4. 本業利益と最終利益の整合性（ウェイト 15.0、実効税率基準 0.60〜0.80）
        profit_ratio, consistency_score = self._calc_profit_consistency_score(
            operating_profit, ordinary_profit, net_profit
        )
        if consistency_score is not None:
            weighted_sum += consistency_score
            weight_sum += 15.0

        # 5. レバレッジ健全性（ウェイト 10.0）
        leverage_ratio, leverage_score = self._calc_leverage_score(roe, roa)
        if leverage_score is not None:
            weighted_sum += leverage_score
            weight_sum += 10.0

        raw_score = 50.0 if weight_sum == 0.0 else (weighted_sum / weight_sum) * 100.0

        metadata: Dict[str, Any] = {
            "operating_cf": operating_cf,
            "free_cash_flow": fcf,
            "operating_cf_margin": ocf_margin,
            "cf_to_net_profit": cf_to_net_profit,
            "fcf_to_assets": fcf_to_assets,
            "net_profit_to_operating_profit_ratio": profit_ratio,
            "roe_to_roa_ratio": leverage_ratio,
            "available_weight": weight_sum,
        }
        return raw_score, metadata

    @staticmethod
    def _calc_accruals_score(
        operating_cf: Optional[float], net_profit: Optional[float]
    ) -> Tuple[Optional[float], Optional[float]]:
        """営業CFによる純利益の裏付け度合い（最大 35.0 点）を評価する。"""
        if operating_cf is None or net_profit is None:
            return None, None
        if net_profit <= 0.0:
            return None, 15.0 if operating_cf > 0.0 else 0.0

        ratio = operating_cf / net_profit
        if not math.isfinite(ratio):
            return None, None
        if ratio <= 0.0:
            return ratio, 0.0
        if ratio < 0.8:
            return ratio, linear_scale(ratio, 0.0, 0.8, 5.0, 25.0)
        if ratio < 1.2:
            return ratio, linear_scale(ratio, 0.8, 1.2, 25.0, 35.0)
        return ratio, 35.0

    @staticmethod
    def _calc_fcf_score(
        fcf: Optional[float],
        total_assets: Optional[float],
        revenue: Optional[float],
    ) -> Tuple[Optional[float], Optional[float]]:
        """フリーCF創出力（最大 25.0 点）を評価する。"""
        if fcf is None:
            return None, None
        if total_assets is not None and total_assets > 0.0:
            fcf_to_assets = fcf / total_assets
            if math.isfinite(fcf_to_assets):
                return fcf_to_assets, linear_scale(fcf_to_assets, -0.05, 0.10, 0.0, 25.0)
        if revenue is not None and revenue > 0.0:
            fcf_margin = fcf / revenue
            if math.isfinite(fcf_margin):
                return None, linear_scale(fcf_margin, -0.05, 0.15, 0.0, 25.0)
        return None, 20.0 if fcf > 0.0 else 5.0

    @staticmethod
    def _calc_ocf_margin_score(ocf_margin: Optional[float]) -> Optional[float]:
        """営業CFマージン（%・最大 15.0 点）を評価する。"""
        if ocf_margin is None:
            return None
        if ocf_margin < 0.0:
            return linear_scale(ocf_margin, -10.0, 0.0, 0.0, 3.0)
        return linear_scale(ocf_margin, 0.0, 20.0, 3.0, 15.0)

    @staticmethod
    def _calc_profit_consistency_score(
        operating_profit: Optional[float],
        ordinary_profit: Optional[float],
        net_profit: Optional[float],
    ) -> Tuple[Optional[float], Optional[float]]:
        """本業利益と最終利益の整合性（最大 15.0 点、実効税率基準 0.60〜0.80）を評価する。"""
        # 金融業等で営業利益が欠損または0以下の場合、経常利益が正であれば代替使用する
        base_profit = operating_profit
        if (base_profit is None or base_profit <= 0.0) and ordinary_profit is not None and ordinary_profit > 0.0:
            base_profit = ordinary_profit

        if base_profit is None or base_profit <= 0.0 or net_profit is None:
            return None, None

        ratio = net_profit / base_profit
        if not math.isfinite(ratio):
            return None, None

        if ratio <= 0.0:
            score = 0.0
        elif ratio < 0.20:
            score = linear_scale(ratio, 0.0, 0.20, 0.0, 3.0)
        elif ratio < 0.45:
            score = linear_scale(ratio, 0.20, 0.45, 3.0, 10.0)
        elif ratio < 0.60:
            score = linear_scale(ratio, 0.45, 0.60, 10.0, 15.0)
        elif ratio <= 0.80:
            score = 15.0
        elif ratio <= 1.00:
            score = linear_scale(ratio, 1.00, 0.80, 10.0, 15.0)
        elif ratio <= 1.40:
            score = linear_scale(ratio, 1.40, 1.00, 3.0, 10.0)
        else:
            score = linear_scale(ratio, 2.0, 1.40, 0.0, 3.0)

        return ratio, score

    @staticmethod
    def _calc_leverage_score(
        roe: Optional[float], roa: Optional[float]
    ) -> Tuple[Optional[float], Optional[float]]:
        """財務レバレッジの健全性（最大 10.0 点）を評価する。"""
        if roa is None or roa <= 0.0 or roe is None:
            return None, None

        leverage = roe / roa
        if not math.isfinite(leverage):
            return None, None

        if leverage <= 0.0:
            score = 0.0
        elif leverage < 1.0:
            score = linear_scale(leverage, 0.0, 1.0, 4.0, 10.0)
        elif leverage <= 2.5:
            score = 10.0
        elif leverage <= 5.0:
            score = linear_scale(leverage, 5.0, 2.5, 2.0, 10.0)
        else:
            score = linear_scale(leverage, 8.0, 5.0, 0.0, 2.0)

        return leverage, score

    def _normalize_score(self, raw_value: float, min_val: float, max_val: float) -> float:
        return normalize_score_range(raw_value, min_val, max_val)


# レジストリに特徴量クラスを登録
feature_registry.register(EarningsQualityScore)
