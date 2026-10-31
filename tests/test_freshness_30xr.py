import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_freshness_30xr as audit

class FreshnessAuditTest(unittest.TestCase):
    def test_existing_metadata_is_parseable(self):
        result = audit.evaluate()
        self.assertIn(result["status"], ("observed", "review_required"))
        self.assertFalse(result["model_enabled"])
        self.assertEqual(result["verified_trade_samples"], 0)

    def test_weekend_not_hard_failed_and_future_date_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            for name, filename in {
                "official": "official_meta.json",
                "historical": "historical_evidence_meta_30q.json",
                "readiness": "research_readiness_meta.json",
                "forward": "forward_observation_meta.json",
                "coverage": "archive_coverage_meta_30r.json",
            }.items():
                source = audit.DATA / filename
                (folder / filename).write_bytes(source.read_bytes())
            now = dt.datetime(2026, 10, 31, 23, 0, tzinfo=ZoneInfo("Asia/Taipei"))
            meta_path = folder / "official_meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["market_dates"] = {"上市": "2026-10-30", "上櫃": "2026-10-30"}
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            result = audit.evaluate(folder, now)
            self.assertEqual(result["status"], "observed")
            self.assertFalse(result["errors"])
            meta["market_dates"]["上市"] = "2026-11-02"
            meta_path.write_text(json.dumps(meta), encoding="utf-8")
            self.assertEqual(audit.evaluate(folder, now)["status"], "fail")

    def test_stale_source_is_review_not_a_fabricated_market_closure(self):
        result = audit.evaluate(now=dt.datetime(2026, 10, 31, 23, 0, tzinfo=ZoneInfo("Asia/Taipei")))
        self.assertEqual(result["status"], "review_required")
        self.assertTrue(result["warnings"])
        self.assertFalse(result["errors"])

if __name__ == "__main__":
    unittest.main()
