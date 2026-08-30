import unittest
from src.common.exceptions import (
    AtlasError,
    DataCollectionError,
    IndicatorCalculationError,
    FeatureCalculationError,
    PatternDetectionError,
    ScoreCalculationError,
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

if __name__ == "__main__":
    unittest.main()
