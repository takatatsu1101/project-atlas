"""東証（東京証券取引所）の営業日カレンダー判定ユーティリティ。

標準ライブラリ（datetime, zoneinfo, functools）のみで日本の国民の祝日、
振替休日、国民の休日、および東証の年末年始休業日（12/31〜1/3）を判定する。
"""

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import FrozenSet, Optional
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_MARKET_CLOSE_CUTOFF = time(15, 35)


def _to_date(d: date) -> date:
    """datetime が渡された場合でも date 型へ正規化する（aware datetime は JST 基準）。"""
    if isinstance(d, datetime):
        if d.tzinfo is not None and d.utcoffset() is not None:
            return d.astimezone(JST).date()
        return d.date()
    return d


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """指定年月の第 n 特定曜日（0=月曜〜6=日曜）の日付を返す。"""
    first_day = date(year, month, 1)
    offset = (weekday - first_day.weekday()) % 7
    day = 1 + offset + (n - 1) * 7
    return date(year, month, day)


def _vernal_equinox_day(year: int) -> int:
    """春分の日（3月）の日を算出する。"""
    if year < 1980:
        return int(20.8357 + 0.242194 * (year - 1980) - int((year - 1983) / 4))
    if year < 2100:
        return int(20.8431 + 0.242194 * (year - 1980) - ((year - 1980) // 4))
    return int(21.8510 + 0.242194 * (year - 1980) - ((year - 1980) // 4))


def _autumnal_equinox_day(year: int) -> int:
    """秋分の日（9月）の日を算出する。"""
    if year < 1980:
        return int(23.2588 + 0.242194 * (year - 1980) - int((year - 1983) / 4))
    if year < 2100:
        return int(23.2488 + 0.242194 * (year - 1980) - ((year - 1980) // 4))
    return int(24.2488 + 0.242194 * (year - 1980) - ((year - 1980) // 4))


@lru_cache(maxsize=64)
def _get_national_holidays_for_year(year: int) -> FrozenSet[date]:
    """指定年の『国民の祝日』（振替休日・国民の休日を除く）の集合を返す。"""
    if year < 1948:
        return frozenset()

    holidays: set[date] = set()

    # 1月: 元日・成人の日
    if year >= 1949:
        holidays.add(date(year, 1, 1))
        if year <= 1999:
            holidays.add(date(year, 1, 15))
        else:
            holidays.add(_nth_weekday_of_month(year, 1, 0, 2))

    # 2月: 建国記念の日・天皇誕生日（令和）
    if year >= 1967:
        holidays.add(date(year, 2, 11))
    if year >= 2020:
        holidays.add(date(year, 2, 23))

    # 3月: 春分の日
    if year >= 1949:
        holidays.add(date(year, 3, _vernal_equinox_day(year)))

    # 4月: 天皇誕生日（昭和） / みどりの日 / 昭和の日
    if 1949 <= year <= 1988:
        holidays.add(date(year, 4, 29))  # 天皇誕生日
    elif 1989 <= year <= 2006:
        holidays.add(date(year, 4, 29))  # みどりの日
    elif year >= 2007:
        holidays.add(date(year, 4, 29))  # 昭和の日

    # 5月: 憲法記念日・みどりの日・こどもの日
    if year >= 1949:
        holidays.add(date(year, 5, 3))
        if year >= 2007:
            holidays.add(date(year, 5, 4))
        holidays.add(date(year, 5, 5))

    # 7月・8月・10月: 海の日・山の日・スポーツの日（2020/2021年五輪特例対応）
    if year == 2020:
        holidays.add(date(2020, 7, 23))  # 海の日
        holidays.add(date(2020, 7, 24))  # スポーツの日
        holidays.add(date(2020, 8, 10))  # 山の日
    elif year == 2021:
        holidays.add(date(2021, 7, 22))  # 海の日
        holidays.add(date(2021, 7, 23))  # スポーツの日
        holidays.add(date(2021, 8, 8))   # 山の日
    else:
        if 1996 <= year <= 2002:
            holidays.add(date(year, 7, 20))
        elif year >= 2003:
            holidays.add(_nth_weekday_of_month(year, 7, 0, 3))

        if year >= 2016:
            holidays.add(date(year, 8, 11))

        if 1966 <= year <= 1999:
            holidays.add(date(year, 10, 10))
        elif year >= 2000:
            holidays.add(_nth_weekday_of_month(year, 10, 0, 2))

    # 9月: 敬老の日・秋分の日
    if 1966 <= year <= 2002:
        holidays.add(date(year, 9, 15))
    elif year >= 2003:
        holidays.add(_nth_weekday_of_month(year, 9, 0, 3))
    holidays.add(date(year, 9, _autumnal_equinox_day(year)))

    # 11月: 文化の日・勤労感謝の日
    holidays.add(date(year, 11, 3))
    holidays.add(date(year, 11, 23))

    # 12月: 天皇誕生日（平成: 1989〜2018年）
    if 1989 <= year <= 2018:
        holidays.add(date(year, 12, 23))

    # 皇室慶弔・改元等の特例休日
    special_holidays = {
        1959: (date(1959, 4, 10),),
        1989: (date(1989, 2, 24),),
        1990: (date(1990, 11, 12),),
        1993: (date(1993, 6, 9),),
        2019: (date(2019, 5, 1), date(2019, 10, 22)),
    }
    if year in special_holidays:
        holidays.update(special_holidays[year])

    return frozenset(holidays)


def _is_national_holiday(d: date) -> bool:
    """国民の祝日（振替休日・国民の休日を除く）かどうかを返す。"""
    return d in _get_national_holidays_for_year(d.year)


def is_japanese_holiday(d: date) -> bool:
    """日本の国民の祝日、振替休日、または国民の休日であるかを判定する。"""
    target = _to_date(d)

    if _is_national_holiday(target):
        return True

    # 振替休日: 日曜日の祝日に連続する国民の祝日の翌平日（2007年以降は全祝日を遡及、旧法は月曜のみ）
    if target.year >= 2007:
        cur = target - timedelta(days=1)
        while _is_national_holiday(cur):
            if cur.weekday() == 6:
                return True
            cur -= timedelta(days=1)
    elif target >= date(1973, 4, 12) and target.weekday() == 0:
        if _is_national_holiday(target - timedelta(days=1)):
            return True

    # 国民の休日: 前日と翌日がともに国民の祝日（振替休日除く）である平日
    if target.year >= 1986 and target.weekday() < 5:
        if _is_national_holiday(target - timedelta(days=1)) and _is_national_holiday(
            target + timedelta(days=1)
        ):
            return True

    return False


def is_tse_trading_day(d: date) -> bool:
    """指定日が東京証券取引所の通常営業日であるかを判定する。"""
    target = _to_date(d)
    if target.weekday() >= 5:
        return False
    if (target.month == 12 and target.day == 31) or (
        target.month == 1 and target.day in (1, 2, 3)
    ):
        return False
    if is_japanese_holiday(target):
        return False
    return True


def get_first_trading_day_on_or_after(d: date) -> date:
    """指定日以降の最初の東証営業日を返す。"""
    cur = _to_date(d)
    while not is_tse_trading_day(cur):
        cur += timedelta(days=1)
    return cur


def get_last_trading_day_on_or_before(d: date) -> date:
    """指定日以前の直近の東証営業日を返す。"""
    cur = _to_date(d)
    while not is_tse_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def get_latest_completed_trading_day(
    ref_date: Optional[date] = None,
    now: Optional[datetime] = None,
    market_close_cutoff: time = DEFAULT_MARKET_CLOSE_CUTOFF,
) -> date:
    """JST 基準で大引け確定済みの最新東証営業日を返す。

    Args:
        ref_date: 基準日。None の場合は現在 JST 日付を使用する。
        now: 現在時刻。None の場合は datetime.now(ZoneInfo("Asia/Tokyo")) を使用する。
            naive datetime は JST として扱い、aware datetime は JST へ変換する。
        market_close_cutoff: 当日分の取引確定とみなす JST 時刻（既定: 15:35）。
    """
    if now is None:
        now_jst = datetime.now(JST)
    elif now.tzinfo is None or now.utcoffset() is None:
        now_jst = now.replace(tzinfo=JST)
    else:
        now_jst = now.astimezone(JST)

    today_jst = now_jst.date()
    target = _to_date(ref_date) if ref_date is not None else today_jst

    if target > today_jst:
        target = today_jst

    if target == today_jst and now_jst.time() < market_close_cutoff:
        target = target - timedelta(days=1)

    return get_last_trading_day_on_or_before(target)
