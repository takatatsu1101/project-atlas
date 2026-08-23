
from typing import List, Dict, Any
from src.model.data_models import ScoreResultModel

class Screener:
    def apply_screener(self, score_results: List[ScoreResultModel], criteria: Dict[str, Any]) -> List[ScoreResultModel]:
        """
        指定された条件でスコア結果をフィルタリングし、合致する銘柄のリストを返す。
        """
        if not score_results:
            return []

        filtered_results = []
        for result in score_results:
            # 総合スコアによるフィルタリング (例: total_scoreがmin_score以上)
            min_score = criteria.get("min_total_score", 0)
            if result.total_score < min_score:
                continue

            # その他の条件（例: サブスコアの範囲、特定のメタデータの有無など）はcriteriaの内容に応じて追加
            # 例: 特定のfeature_idのスコアが閾値以上
            # if "min_feature_score_F001_TrendStrength" in criteria:
            #     # feature_setsが必要になるため、ScoreResultModelにFeatureResultModelを保持する必要がある
            #     pass

            filtered_results.append(result)
        
        print(f"スクリーニングが完了しました。{len(filtered_results)} 件の銘柄が抽出されました。")
        return filtered_results

# モジュールレベルでインスタンス化
screener = Screener()

def apply_screener(score_results: List[ScoreResultModel], criteria: Dict[str, Any]) -> List[ScoreResultModel]:
    return screener.apply_screener(score_results, criteria)
