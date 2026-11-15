import subprocess
import sys
import unittest
from pathlib import Path

import src.pattern_detector
from src.pattern_detector.registry import pattern_registry


class TestPatternRegistryAutoload(unittest.TestCase):
    def test_autoload_registers_all_three_patterns(self):
        """import src.pattern_detector だけで全3パターンが自動登録される"""
        registered_ids = {p["pattern_id"] for p in pattern_registry.list_patterns()}
        self.assertIn("P001_Hammer", registered_ids)
        self.assertIn("R001_DoubleBottom", registered_ids)
        self.assertIn("R002_DoubleTop", registered_ids)

    def test_autoload_in_fresh_python_process(self):
        """他モジュールに依存せず import src.pattern_detector 単体で全3パターンが登録される"""
        project_root = Path(__file__).resolve().parents[3]
        code = (
            "import src.pattern_detector; "
            "from src.pattern_detector.registry import pattern_registry; "
            "ids = sorted(p['pattern_id'] for p in pattern_registry.list_patterns()); "
            "print(','.join(ids))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=True,
        )
        ids = proc.stdout.strip().splitlines()[-1].split(",")
        self.assertEqual(
            ids,
            ["P001_Hammer", "R001_DoubleBottom", "R002_DoubleTop"],
        )


if __name__ == "__main__":
    unittest.main()
