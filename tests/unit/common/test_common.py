import unittest
from src.common.exceptions import (
    AtlasError,
    DataCollectionError,
    IndicatorCalculationError,
    FeatureCalculationError,
    PatternDetectionError,
    ScoreCalculationError,
)
from datetime import date
from src.common.indexing import (
    resolve_evaluation_targets,
    resolve_target_indices,
    supports_target_indices,
)
from src.common.logger import get_logger

class TestCommonModules(unittest.TestCase):
    def test_logger(self):
        logger = get_logger("TestLogger")
        self.assertIsNotNone(logger)
        logger.info("Test log message")

    def test_exceptions(self):
        with self.assertRaises(AtlasError):
            raise DataCollectionError("Data collection failed")

        with self.assertRaises(AtlasError):
            raise IndicatorCalculationError("Indicator calculation failed")

        with self.assertRaises(AtlasError):
            raise FeatureCalculationError("Feature calculation failed")

        with self.assertRaises(AtlasError):
            raise PatternDetectionError("Pattern detection failed")

        with self.assertRaises(AtlasError):
            raise ScoreCalculationError("Score calculation failed")

    def test_resolve_target_indices(self):
        self.assertEqual(resolve_target_indices(0, None), [])
        self.assertEqual(resolve_target_indices(4, None), [0, 1, 2, 3])
        self.assertEqual(resolve_target_indices(4, []), [])
        self.assertEqual(resolve_target_indices(5, [-1, -2, 0, -1, 10, -10, True]), [4, 3, 0])

    def test_supports_target_indices(self):
        def fn_plain(a, b):
            pass

        def fn_with_target(a, target_indices=None):
            pass

        def fn_with_kwargs(a, **kwargs):
            pass

        def fn_positional_only(a, target_indices=None, /):
            pass

        self.assertFalse(supports_target_indices(fn_plain))
        self.assertTrue(supports_target_indices(fn_with_target))
        self.assertTrue(supports_target_indices(fn_with_kwargs))
        self.assertFalse(supports_target_indices(fn_positional_only))

    def test_resolve_evaluation_targets(self):
        class _Item:
            def __init__(self, d):
                self.date = d

        items = [_Item(date(2025, 1, 1)), _Item(date(2025, 1, 2)), _Item(date(2025, 1, 3))]
        self.assertEqual(resolve_evaluation_targets(items, latest_only=False), (None, None))
        self.assertEqual(
            resolve_evaluation_targets(items, latest_only=True),
            ([2], {date(2025, 1, 3)}),
        )
        self.assertEqual(
            resolve_evaluation_targets(items, latest_only=True, target_indices=[0, -1]),
            ([0, 2], {date(2025, 1, 1), date(2025, 1, 3)}),
        )
        self.assertEqual(
            resolve_evaluation_targets([], latest_only=True),
            ([], set()),
        )

if __name__ == "__main__":
    unittest.main()
