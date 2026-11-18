import io
import logging
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src.common.logger import (
    get_logger,
    project_log_level,
    restore_project_log_levels,
    set_project_log_level,
)
from src.common.progress import ProgressTracker


class TestProgressTracker(unittest.TestCase):
    def test_total_zero_or_negative_does_nothing(self):
        """total <= 0 の場合は update() で何も出力せず False を返す"""
        for total in (0, -5):
            tracker = ProgressTracker("テスト", total=total)
            buf = io.StringIO()
            with redirect_stdout(buf):
                emitted = tracker.update(1, detail="detail")
            self.assertFalse(emitted)
            self.assertEqual(buf.getvalue(), "")

    def test_small_total_prints_only_on_completion(self):
        """total < 10 の場合は途中経過を出力せず、完了時のみ出力し ETA は付けない"""
        with patch("src.common.progress.time.monotonic", side_effect=[100.0, 100.1, 100.2, 101.5]):
            tracker = ProgressTracker("銘柄評価", total=3, step_percent=10, min_interval_sec=2.0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertFalse(tracker.update(1, detail="通過=1"))
                self.assertFalse(tracker.update(2, detail="通過=2"))
                self.assertTrue(tracker.update(3, detail="通過=3"))

        output = buf.getvalue().strip()
        self.assertIn("[進行度] 銘柄評価: 3/3 (100.0%) [通過=3] | 経過 1.5s", output)
        self.assertNotIn("残り目安", output)

    def test_step_percent_and_eta_output(self):
        """total >= 10 では step_percent 刻みで出力され、未完了かつ経過 > 0 なら残り目安を表示する"""
        # 初期時刻 0.0s、以降 0.5s ずつ経過する（min_interval_sec=10.0 なのでパーセント条件のみで発火）
        times = [float(i) * 0.5 for i in range(25)]
        with patch("src.common.progress.time.monotonic", side_effect=times):
            tracker = ProgressTracker("銘柄評価", total=20, step_percent=10, min_interval_sec=10.0)
            buf = io.StringIO()
            emitted_steps = []
            with redirect_stdout(buf):
                for completed in range(1, 21):
                    if tracker.update(completed):
                        emitted_steps.append(completed)
                # 完了後の重複呼び出しは無視されること
                self.assertFalse(tracker.update(20))

        # 20件・10%刻みなので 2, 4, 6, ..., 20 の10回出力される
        self.assertEqual(emitted_steps, [2, 4, 6, 8, 10, 12, 14, 16, 18, 20])
        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 10)
        self.assertIn("[進行度] 銘柄評価: 2/20 (10.0%) | 経過 1.0s (残り目安 9.0s)", lines[0])
        self.assertIn("[進行度] 銘柄評価: 20/20 (100.0%) | 経過 10.0s", lines[-1])
        self.assertNotIn("残り目安", lines[-1])

    def test_min_interval_sec_triggers_output_even_below_step_percent(self):
        """step_percent 未満の進捗でも min_interval_sec 経過時に出力される"""
        with patch("src.common.progress.time.monotonic", side_effect=[10.0, 12.5, 13.0, 15.0]):
            tracker = ProgressTracker("銘柄評価", total=100, step_percent=10, min_interval_sec=2.0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(tracker.update(1, detail="通過=1"))
                self.assertFalse(tracker.update(2, detail="通過=2"))
                self.assertTrue(tracker.update(3, detail="通過=3"))

        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("1/100 (1.0%) [通過=1] | 経過 2.5s (残り目安 247.5s)", lines[0])
        self.assertIn("3/100 (3.0%) [通過=3] | 経過 5.0s (残り目安 161.7s)", lines[1])

    def test_small_total_emits_when_min_interval_elapsed(self):
        """total < 10 でも min_interval_sec 以上経過すれば途中進捗が出力される"""
        with patch("src.common.progress.time.monotonic", side_effect=[10.0, 12.5, 13.0, 15.0]):
            tracker = ProgressTracker("銘柄評価", total=5, step_percent=10, min_interval_sec=2.0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(tracker.update(1, detail="通過=1"))
                self.assertFalse(tracker.update(2, detail="通過=2"))
                self.assertTrue(tracker.update(5, detail="通過=5"))

        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn("1/5 (20.0%) [通過=1] | 経過 2.5s (残り目安 10.0s)", lines[0])
        self.assertIn("5/5 (100.0%) [通過=5] | 経過 5.0s", lines[1])
        self.assertNotIn("残り目安", lines[1])

    def test_edge_cases_clamping_bounds_and_zero_elapsed(self):
        """step_percent <= 0 のクランプ、completed <= 0、completed > total、elapsed == 0.0 を検証する"""
        # 1. step_percent <= 0 は 1 へクランプされ、1% ごとに出力される
        times = [0.0, 1.0, 2.0]
        with patch("src.common.progress.time.monotonic", side_effect=times):
            tracker = ProgressTracker("クランプ検証", total=100, step_percent=0, min_interval_sec=60.0)
            self.assertEqual(tracker.step_percent, 1)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(tracker.update(1))
                self.assertTrue(tracker.update(2))
            self.assertEqual(len(buf.getvalue().splitlines()), 2)

        tracker_neg = ProgressTracker("負値クランプ", total=100, step_percent=-5)
        self.assertEqual(tracker_neg.step_percent, 1)

        # 2. completed <= 0 は出力せず False を返す
        with patch("src.common.progress.time.monotonic", side_effect=[10.0, 15.0, 20.0]):
            tracker_zero = ProgressTracker("境界", total=10, min_interval_sec=1.0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertFalse(tracker_zero.update(0))
                self.assertFalse(tracker_zero.update(-3))
            self.assertEqual(buf.getvalue(), "")

        # 3. completed > total は total/total (100.0%) に丸められ、完了扱いになる
        with patch("src.common.progress.time.monotonic", side_effect=[10.0, 12.0]):
            tracker_over = ProgressTracker("超過丸め", total=5)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(tracker_over.update(8, detail="超過"))
                self.assertFalse(tracker_over.update(9))
            output = buf.getvalue().strip()
            self.assertIn("5/5 (100.0%) [超過] | 経過 2.0s", output)
            self.assertNotIn("残り目安", output)

        # 4. elapsed == 0.0 では未完了でも ETA（残り目安）を表示しない
        with patch("src.common.progress.time.monotonic", side_effect=[50.0, 50.0]):
            tracker_instant = ProgressTracker("ゼロ経過", total=20, step_percent=10, min_interval_sec=10.0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertTrue(tracker_instant.update(2))
            output = buf.getvalue().strip()
            self.assertIn("2/20 (10.0%) | 経過 0.0s", output)
            self.assertNotIn("残り目安", output)


class TestProjectLogLevel(unittest.TestCase):
    def test_project_log_level_context_switches_and_restores(self):
        """project_log_level がプロジェクト系ロガーとハンドラのレベルを切り替え、終了後に復元する"""
        proj_logger = get_logger("src.common.progress_test")
        legacy_logger = get_logger("DataCollector")
        external_logger = logging.getLogger("external.third_party.test")
        external_logger.setLevel(logging.WARNING)

        orig_proj_level = proj_logger.level
        orig_legacy_level = legacy_logger.level
        # ハンドラレベルが一時的に WARNING であっても DEBUG へ切り替えられ、その後復元されること
        temp_handler = logging.StreamHandler(io.StringIO())
        temp_handler.setLevel(logging.WARNING)
        proj_logger.addHandler(temp_handler)
        try:
            with project_log_level(logging.DEBUG):
                self.assertEqual(proj_logger.level, logging.DEBUG)
                self.assertEqual(legacy_logger.level, logging.DEBUG)
                self.assertEqual(temp_handler.level, logging.DEBUG)
                self.assertEqual(external_logger.level, logging.WARNING)

                dynamic_logger = get_logger("src.common.dynamic_test")
                self.assertEqual(dynamic_logger.level, logging.DEBUG)

            self.assertEqual(proj_logger.level, orig_proj_level)
            self.assertEqual(legacy_logger.level, orig_legacy_level)
            self.assertEqual(dynamic_logger.level, logging.INFO)
            self.assertEqual(temp_handler.level, logging.WARNING)
            self.assertEqual(external_logger.level, logging.WARNING)
        finally:
            proj_logger.removeHandler(temp_handler)

    def test_nested_project_log_level_restores_dynamic_logger(self):
        """ネストされた project_log_level でもブロック内で生成したロガーが段階的に復元される"""
        outer_logger = get_logger("src.common.nested_outer_test")
        outer_logger.setLevel(logging.INFO)

        with project_log_level(logging.WARNING):
            self.assertEqual(outer_logger.level, logging.WARNING)
            dynamic_outer = get_logger("src.common.dynamic_nested_outer_test")
            self.assertEqual(dynamic_outer.level, logging.WARNING)

            with project_log_level(logging.DEBUG):
                self.assertEqual(outer_logger.level, logging.DEBUG)
                self.assertEqual(dynamic_outer.level, logging.DEBUG)
                dynamic_inner = get_logger("src.common.dynamic_nested_inner_test")
                self.assertEqual(dynamic_inner.level, logging.DEBUG)

            # 内側終了後は外側のレベル（WARNING）へ戻る
            self.assertEqual(outer_logger.level, logging.WARNING)
            self.assertEqual(dynamic_outer.level, logging.WARNING)
            self.assertEqual(dynamic_inner.level, logging.WARNING)

        # 外側終了後は INFO へ戻る
        self.assertEqual(outer_logger.level, logging.INFO)
        self.assertEqual(dynamic_outer.level, logging.INFO)
        self.assertEqual(dynamic_inner.level, logging.INFO)

    def test_set_project_log_level_safe_with_placeholder_in_logger_dict(self):
        """loggerDict に logging.PlaceHolder が存在しても set/restore が安全に動作する"""
        # 親パッケージ名を loggerDict 上で PlaceHolder として登録させる
        leaf_logger = get_logger("src.placeholder_pkg_test.sub.leaf")
        leaf_logger.setLevel(logging.INFO)
        placeholder = logging.Logger.manager.loggerDict.get("src.placeholder_pkg_test")
        self.assertIsInstance(placeholder, logging.PlaceHolder)

        snapshot = set_project_log_level(logging.DEBUG)
        try:
            self.assertEqual(leaf_logger.level, logging.DEBUG)
            self.assertIsInstance(
                logging.Logger.manager.loggerDict.get("src.placeholder_pkg_test"),
                logging.PlaceHolder,
            )
        finally:
            restore_project_log_levels(snapshot)

        self.assertEqual(leaf_logger.level, logging.INFO)

    def test_project_log_level_restores_on_exception(self):
        """with ブロック内で例外が発生しても元のログレベルへ復元される"""
        proj_logger = get_logger("src.common.progress_exc_test")
        proj_logger.setLevel(logging.INFO)

        with self.assertRaises(RuntimeError):
            with project_log_level(logging.DEBUG):
                self.assertEqual(proj_logger.level, logging.DEBUG)
                raise RuntimeError("boom")

        self.assertEqual(proj_logger.level, logging.INFO)

    def test_set_and_restore_project_log_level_explicit(self):
        """set_project_log_level と restore_project_log_levels で明示的な切り替え・復元ができる"""
        proj_logger = get_logger("src.common.progress_explicit_test")
        proj_logger.setLevel(logging.INFO)
        snapshot = set_project_log_level(logging.DEBUG)
        try:
            self.assertEqual(proj_logger.level, logging.DEBUG)
        finally:
            restore_project_log_levels(snapshot)
        self.assertEqual(proj_logger.level, logging.INFO)


if __name__ == "__main__":
    unittest.main()
