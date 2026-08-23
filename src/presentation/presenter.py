
from typing import List
from src.model.data_models import AnalysisResultModel

class Presenter:
    def display_results(self, analysis_results: List[AnalysisResultModel], output_type: str = "cli") -> None:
        """
        分析結果をCLIまたは将来的なGUIで表示する。
        """
        if not analysis_results:
            print("表示する分析結果がありません。")
            return

        if output_type == "cli":
            self._display_cli(analysis_results)
        elif output_type == "gui":
            print("GUI表示は未実装です。CLIで表示します。")
            self._display_cli(analysis_results)
        else:
            print(f"不明な出力タイプ: {output_type}。CLIで表示します。")
            self._display_cli(analysis_results)

    def _display_cli(self, analysis_results: List[AnalysisResultModel]) -> None:
        """
        CLI形式で結果を出力する。
        """
        print("\n--- Project Atlas 分析結果 --- ")
        for result in analysis_results:
            print(f"\n銘柄コード: {result.symbol} ({result.company_name})")
            print(f"総合スコア: {result.total_score:.2f}")
            if result.rank is not None:
                print(f"ランキング: {result.rank} 位")
            if result.summary:
                print(f"サマリー: {result.summary}")
            
            if result.feature_results:
                print("  --- 特徴量 --- ")
                for fr in result.feature_results:
                    print(f"    - {fr.feature_name} ({fr.feature_id}): スコア {fr.score:.2f} (生値: {fr.raw_value:.2f})")
            
            if result.pattern_results:
                print("  --- 検出パターン --- ")
                for pr in result.pattern_results:
                    print(f"    - {pr.pattern_name} ({pr.pattern_id}): 信頼度 {pr.confidence:.2f}")
        print("------------------------------")

# モジュールレベルでインスタンス化
presenter = Presenter()

def display_results(analysis_results: List[AnalysisResultModel], output_type: str = "cli") -> None:
    return presenter.display_results(analysis_results, output_type)
