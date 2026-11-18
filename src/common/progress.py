"""
進捗状況（%・件数・経過時間・残り目安時間）を適度な間隔でコンソール出力する共通トラッカー。
"""

import time


class ProgressTracker:
    """処理件数と経過時間に応じて進捗状況を標準出力へ出力するトラッカー。"""

    def __init__(
        self,
        label: str,
        total: int,
        step_percent: int = 10,
        min_interval_sec: float = 2.0,
    ) -> None:
        self.label = label
        self.total = int(total)
        self.step_percent = max(1, int(step_percent))
        self.min_interval_sec = max(0.0, float(min_interval_sec))
        self._start_time = time.monotonic()
        self._last_report_time = self._start_time
        self._last_reported_pct = 0.0
        self._finished = False

    def update(self, completed: int, detail: str = "") -> bool:
        """
        現在の完了件数を通知し、出力条件を満たした場合に進行度行を出力する。
        出力を行った場合は True、スキップした場合は False を返す。
        """
        if self.total <= 0 or completed <= 0 or self._finished:
            return False

        now = time.monotonic()
        display_completed = min(int(completed), self.total)
        is_complete = completed >= self.total
        pct = (display_completed / self.total) * 100.0

        should_report = False
        if is_complete:
            should_report = True
        else:
            pct_advanced = (self.total >= 10) and (
                (pct - self._last_reported_pct) >= self.step_percent
            )
            interval_elapsed = (now - self._last_report_time) >= self.min_interval_sec
            should_report = pct_advanced or interval_elapsed

        if not should_report:
            return False

        elapsed = max(0.0, now - self._start_time)
        detail_part = f" [{detail}]" if detail else ""
        eta_part = ""
        if not is_complete and display_completed > 0 and elapsed > 0.0:
            eta = elapsed * (self.total - display_completed) / display_completed
            eta_part = f" (残り目安 {eta:.1f}s)"

        print(
            f"[進行度] {self.label}: {display_completed}/{self.total} ({pct:.1f}%)"
            f"{detail_part} | 経過 {elapsed:.1f}s{eta_part}",
            flush=True,
        )

        self._last_report_time = now
        self._last_reported_pct = pct
        if is_complete:
            self._finished = True
        return True
