
from typing import List, Dict, Optional
from src.model.data_models import ScoreResultModel, AnalysisResultModel

class RankingGenerator:
    def generate_ranking(self, filtered_score_results: List[ScoreResultModel]) -> List[AnalysisResultModel]:
        """
        フィルタリングされたスコア結果からランキングを生成し、最終分析結果のリストを返す。
        """
        if not filtered_score_results:
            return []

        # total_scoreで降順にソート
        sorted_results = sorted(filtered_score_results, key=lambda x: x.total_score, reverse=True)

        analysis_results: List[AnalysisResultModel] = []
        for i, score_result in enumerate(sorted_results):
            # ここで企業名を取得するロジックが必要だが、今回はダミー
            company_name = f"Company_{score_result.symbol}"

            # ScoreResultModelにはfeature_resultsやpattern_resultsが含まれていないため、
            # 必要であればここで再構築するか、ScoreResultModelを拡張する必要がある。
            # 今回はAnalysisResultModelのfeature_resultsとpattern_resultsは空リストとする。
            analysis_results.append(AnalysisResultModel(
                symbol=score_result.symbol,
                company_name=company_name,
                total_score=score_result.total_score,
                feature_results=[],  # 現在のScoreResultModelからは取得できない
                pattern_results=[],  # 現在のScoreResultModelからは取得できない
                rank=i + 1,
                summary=f"{company_name} は総合スコア {score_result.total_score:.2f} でランク {i+1} 位です。"
            ))
        
        print(f"ランキングを生成しました。{len(analysis_results)} 件の分析結果。")
        return analysis_results

# モジュールレベルでインスタンス化
ranking_generator = RankingGenerator()

def generate_ranking(filtered_score_results: List[ScoreResultModel]) -> List[AnalysisResultModel]:
    return ranking_generator.generate_ranking(filtered_score_results)
