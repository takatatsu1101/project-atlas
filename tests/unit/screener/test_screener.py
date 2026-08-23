import unittest
from datetime import datetime
from src.screener.screener import Screener
from src.ranking.generator import RankingGenerator
from src.model.data_models import ScoreResultModel

class TestScreenerAndRanking(unittest.TestCase):
    def test_screener_filtering(self):
        screener = Screener()
        results = [
            ScoreResultModel(symbol="7203.T", date=datetime(2026, 1, 1), total_score=85.0, sub_scores={}, metadata={}),
            ScoreResultModel(symbol="9984.T", date=datetime(2026, 1, 1), total_score=55.0, sub_scores={}, metadata={}),
            ScoreResultModel(symbol="6758.T", date=datetime(2026, 1, 1), total_score=70.0, sub_scores={}, metadata={}),
        ]
        
        # 閾値 70 以上でフィルタリング
        filtered = screener.apply_screener(results, {"min_total_score": 70.0})
        self.assertEqual(len(filtered), 2)
        symbols = [r.symbol for r in filtered]
        self.assertIn("7203.T", symbols)
        self.assertIn("6758.T", symbols)
        self.assertNotIn("9984.T", symbols)

    def test_ranking_generator(self):
        generator = RankingGenerator()
        results = [
            ScoreResultModel(symbol="6758.T", date=datetime(2026, 1, 1), total_score=70.0, sub_scores={}, metadata={}),
            ScoreResultModel(symbol="7203.T", date=datetime(2026, 1, 1), total_score=90.0, sub_scores={}, metadata={}),
        ]
        
        ranking = generator.generate_ranking(results)
        self.assertEqual(len(ranking), 2)
        # 降順ソートの確認 (最高得点が1位)
        self.assertEqual(ranking[0].symbol, "7203.T")
        self.assertEqual(ranking[0].rank, 1)
        self.assertEqual(ranking[1].symbol, "6758.T")
        self.assertEqual(ranking[1].rank, 2)

if __name__ == "__main__":
    unittest.main()
