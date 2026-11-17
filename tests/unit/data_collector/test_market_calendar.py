import unittest
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from src.data_collector.market_calendar import (
    get_first_trading_day_on_or_after,
    get_last_trading_day_on_or_before,
    get_latest_completed_trading_day,
    is_japanese_holiday,
    is_tse_trading_day,
)

JST = ZoneInfo("Asia/Tokyo")


class TestMarketCalendar(unittest.TestCase):
    def test_fixed_and_happy_monday_holidays(self):
        """固定祝日・ハッピーマンデー・天皇誕生日の変遷を正確に判定する"""
        # 2025年の主要祝日
        self.assertTrue(is_japanese_holiday(date(2025, 1, 1)))    # 元日
        self.assertTrue(is_japanese_holiday(date(2025, 1, 13)))   # 成人の日（1月第2月曜）
        self.assertTrue(is_japanese_holiday(date(2025, 2, 11)))   # 建国記念の日
        self.assertTrue(is_japanese_holiday(date(2025, 2, 23)))   # 天皇誕生日（令和）
        self.assertTrue(is_japanese_holiday(date(2025, 4, 29)))   # 昭和の日
        self.assertTrue(is_japanese_holiday(date(2025, 5, 3)))    # 憲法記念日
        self.assertTrue(is_japanese_holiday(date(2025, 5, 4)))    # みどりの日
        self.assertTrue(is_japanese_holiday(date(2025, 5, 5)))    # こどもの日
        self.assertTrue(is_japanese_holiday(date(2025, 7, 21)))   # 海の日（7月第3月曜）
        self.assertTrue(is_japanese_holiday(date(2025, 8, 11)))   # 山の日
        self.assertTrue(is_japanese_holiday(date(2025, 9, 15)))   # 敬老の日（9月第3月曜）
        self.assertTrue(is_japanese_holiday(date(2025, 10, 13)))  # スポーツの日（10月第2月曜）
        self.assertTrue(is_japanese_holiday(date(2025, 11, 3)))   # 文化の日
        self.assertTrue(is_japanese_holiday(date(2025, 11, 23)))  # 勤労感謝の日

        # 平成天皇誕生日（2018年は祝日、2019年以降は祝日ではない）
        self.assertTrue(is_japanese_holiday(date(2018, 12, 23)))
        self.assertFalse(is_japanese_holiday(date(2019, 12, 23)))
        self.assertFalse(is_japanese_holiday(date(2025, 12, 23)))
        self.assertFalse(is_japanese_holiday(date(2019, 2, 23)))

        # 通常平日
        self.assertFalse(is_japanese_holiday(date(2025, 1, 6)))
        self.assertFalse(is_japanese_holiday(date(2025, 6, 10)))

    def test_equinox_holidays(self):
        """春分の日・秋分の日を正確に判定する"""
        self.assertTrue(is_japanese_holiday(date(2024, 3, 20)))
        self.assertTrue(is_japanese_holiday(date(2024, 9, 22)))
        self.assertTrue(is_japanese_holiday(date(2025, 3, 20)))
        self.assertTrue(is_japanese_holiday(date(2025, 9, 23)))
        self.assertTrue(is_japanese_holiday(date(2026, 3, 20)))
        self.assertTrue(is_japanese_holiday(date(2026, 9, 23)))

    def test_substitute_holidays(self):
        """振替休日（日曜祝日の翌平日、GW連休跨ぎ含む）を正確に判定する"""
        # 2025年2月23日(日: 天皇誕生日) -> 2月24日(月)が振替休日
        self.assertTrue(is_japanese_holiday(date(2025, 2, 24)))
        # 2025年5月4日(日: みどりの日), 5月5日(月: こどもの日) -> 5月6日(火)が振替休日
        self.assertTrue(is_japanese_holiday(date(2025, 5, 6)))
        # 2026年5月3日(日: 憲法記念日), 5月4日(月), 5月5日(火) -> 5月6日(水)が振替休日
        self.assertTrue(is_japanese_holiday(date(2026, 5, 6)))
        # 2025年11月23日(日: 勤労感謝の日) -> 11月24日(月)が振替休日
        self.assertTrue(is_japanese_holiday(date(2025, 11, 24)))

    def test_citizens_holidays_and_2019_special(self):
        """2019年改元特例と国民の休日（前日・翌日が国民の祝日の平日）を判定する"""
        # 2019年GW 10連休の祝日・国民の休日・振替休日
        self.assertTrue(is_japanese_holiday(date(2019, 4, 29)))  # 昭和の日
        self.assertTrue(is_japanese_holiday(date(2019, 4, 30)))  # 国民の休日
        self.assertTrue(is_japanese_holiday(date(2019, 5, 1)))   # 天皇の即位の日
        self.assertTrue(is_japanese_holiday(date(2019, 5, 2)))   # 国民の休日
        self.assertTrue(is_japanese_holiday(date(2019, 5, 3)))   # 憲法記念日
        self.assertTrue(is_japanese_holiday(date(2019, 5, 6)))   # 振替休日
        self.assertTrue(is_japanese_holiday(date(2019, 10, 22))) # 即位礼正殿の儀

        # 2026年9月: 9/21(月: 敬老の日), 9/22(火: 国民の休日), 9/23(水: 秋分の日)
        self.assertTrue(is_japanese_holiday(date(2026, 9, 21)))
        self.assertTrue(is_japanese_holiday(date(2026, 9, 22)))
        self.assertTrue(is_japanese_holiday(date(2026, 9, 23)))

        # 振替休日にはさまれても国民の休日にならない例（例: 2024年9月23日(月)は9/22(日)秋分の日の振替休日、9/24(火)は平日）
        self.assertTrue(is_japanese_holiday(date(2024, 9, 23)))
        self.assertFalse(is_japanese_holiday(date(2024, 9, 24)))

    def test_2020_2021_olympic_holidays(self):
        """2020年・2021年の東京五輪特例祝日を判定する"""
        # 2020年: 海の日(7/23), スポーツの日(7/24), 山の日(8/10) に移動
        self.assertTrue(is_japanese_holiday(date(2020, 7, 23)))
        self.assertTrue(is_japanese_holiday(date(2020, 7, 24)))
        self.assertTrue(is_japanese_holiday(date(2020, 8, 10)))
        self.assertFalse(is_japanese_holiday(date(2020, 7, 20)))  # 通常7月第3月曜は平日
        self.assertFalse(is_japanese_holiday(date(2020, 8, 11)))  # 通常山の日も平日
        self.assertFalse(is_japanese_holiday(date(2020, 10, 12))) # 通常スポーツの日も平日

        # 2021年: 海の日(7/22), スポーツの日(7/23), 山の日(8/8日 -> 8/9月振替休日)
        self.assertTrue(is_japanese_holiday(date(2021, 7, 22)))
        self.assertTrue(is_japanese_holiday(date(2021, 7, 23)))
        self.assertTrue(is_japanese_holiday(date(2021, 8, 8)))
        self.assertTrue(is_japanese_holiday(date(2021, 8, 9)))
        self.assertFalse(is_japanese_holiday(date(2021, 7, 19)))
        self.assertFalse(is_japanese_holiday(date(2021, 8, 11)))
        self.assertFalse(is_japanese_holiday(date(2021, 10, 11)))

    def test_tse_trading_day_and_navigation(self):
        """東証営業日（土日・年末年始・祝日除外）と前後営業日取得を検証する"""
        # 2024年末〜2025年始: 12/30(月)は大納会、12/31〜1/3は休場、1/4(土), 1/5(日)休場、1/6(月)は大発会
        self.assertTrue(is_tse_trading_day(date(2024, 12, 30)))
        self.assertFalse(is_tse_trading_day(date(2024, 12, 31)))
        self.assertFalse(is_tse_trading_day(date(2025, 1, 1)))
        self.assertFalse(is_tse_trading_day(date(2025, 1, 2)))
        self.assertFalse(is_tse_trading_day(date(2025, 1, 3)))
        self.assertFalse(is_tse_trading_day(date(2025, 1, 4)))
        self.assertFalse(is_tse_trading_day(date(2025, 1, 5)))
        self.assertTrue(is_tse_trading_day(date(2025, 1, 6)))

        # 平日でも1/2・1/3・12/31は休場（2026年1月2日(金), 2025年12月31日(水)）
        self.assertFalse(is_tse_trading_day(date(2025, 12, 31)))
        self.assertFalse(is_tse_trading_day(date(2026, 1, 2)))

        self.assertEqual(get_first_trading_day_on_or_after(date(2025, 1, 1)), date(2025, 1, 6))
        self.assertEqual(get_first_trading_day_on_or_after(date(2025, 1, 6)), date(2025, 1, 6))
        self.assertEqual(get_last_trading_day_on_or_before(date(2025, 1, 5)), date(2024, 12, 30))
        self.assertEqual(get_last_trading_day_on_or_before(date(2024, 12, 30)), date(2024, 12, 30))

    def test_get_latest_completed_trading_day_jst_cutoff_and_bounds(self):
        """JST 場中/大引け後境界、UTC変換、未来日丸め、休場日判定を検証する"""
        # 2026-11-17(火: 営業日) 場中 15:34 JST -> 前営業日 2026-11-16(月)
        self.assertEqual(
            get_latest_completed_trading_day(
                now=datetime(2026, 11, 17, 15, 34, tzinfo=JST)
            ),
            date(2026, 11, 16),
        )
        # 2026-11-17(火: 営業日) 大引け後 15:35 JST -> 当日 2026-11-17
        self.assertEqual(
            get_latest_completed_trading_day(
                now=datetime(2026, 11, 17, 15, 35, tzinfo=JST)
            ),
            date(2026, 11, 17),
        )
        # naive datetime は JST として解釈
        self.assertEqual(
            get_latest_completed_trading_day(
                now=datetime(2026, 11, 17, 10, 0)
            ),
            date(2026, 11, 16),
        )
        # aware UTC datetime (06:34 UTC = 15:34 JST / 06:35 UTC = 15:35 JST)
        self.assertEqual(
            get_latest_completed_trading_day(
                now=datetime(2026, 11, 17, 6, 34, tzinfo=timezone.utc)
            ),
            date(2026, 11, 16),
        )
        self.assertEqual(
            get_latest_completed_trading_day(
                now=datetime(2026, 11, 17, 6, 35, tzinfo=timezone.utc)
            ),
            date(2026, 11, 17),
        )

        # ref_date が未来日の場合は当日 JST に丸められ、場中判定も適用される
        self.assertEqual(
            get_latest_completed_trading_day(
                ref_date=date(2026, 12, 31),
                now=datetime(2026, 11, 17, 12, 0, tzinfo=JST),
            ),
            date(2026, 11, 16),
        )

        # ref_date が過去の休場日（2026-09-22 国民の休日）の場合は直前営業日 2026-09-18(金)
        self.assertEqual(
            get_latest_completed_trading_day(
                ref_date=date(2026, 9, 22),
                now=datetime(2026, 11, 17, 12, 0, tzinfo=JST),
            ),
            date(2026, 9, 18),
        )

        # ref_date が aware datetime の場合は JST 日付へ変換して判定する
        # 2026-11-12 20:00 UTC == 2026-11-13 05:00 JST (金曜日)
        self.assertEqual(
            get_latest_completed_trading_day(
                ref_date=datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc),
                now=datetime(2026, 11, 17, 12, 0, tzinfo=JST),
            ),
            date(2026, 11, 13),
        )

        # カスタムカットオフ時刻
        self.assertEqual(
            get_latest_completed_trading_day(
                now=datetime(2026, 11, 17, 15, 0, tzinfo=JST),
                market_close_cutoff=time(15, 0),
            ),
            date(2026, 11, 17),
        )


if __name__ == "__main__":
    unittest.main()
