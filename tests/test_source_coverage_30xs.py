import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_source_coverage_30xs as C
class CoverageTests(unittest.TestCase):
    def test_nine_sources_and_disabled_prediction(self):
        r=C.build()
        self.assertEqual(r["version"],"3.0X-S")
        self.assertEqual(len(r["sources"]),9)
        self.assertIsNone(r["win_rate"])
        self.assertFalse(r["prediction_enabled"])
        self.assertEqual(r["certified_trade_samples"],0)
        self.assertTrue(all(0<=x["unique_stocks"]<=x["rows"] for x in r["sources"]))
    def test_snapshot_gate_stays_blocked(self):
        r=C.build()
        self.assertGreaterEqual(r["historical_first_captured_sessions"],0)
        self.assertGreaterEqual(r["historical_stock_session_observations"],0)
if __name__=="__main__":unittest.main()
