"""3.0F production probability gate: real repository evidence + negative fixtures."""
import datetime as dt
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.prediction_readiness_30f import DATA, REQUIRED, audit, write_report

class PredictionReadinessTests(unittest.TestCase):
    def test_live_evidence_remains_blocked(self):
        m = audit(DATA, dt.datetime(2026, 10, 28, tzinfo=dt.timezone.utc))
        self.assertEqual(m["status"], "blocked_evidence_not_ready")
        self.assertFalse(m["production_win_rate_enabled"])
        self.assertFalse(m["production_stock_probability_enabled"])
        self.assertEqual(m["verified_outcome_samples_for_model"], 0)
        self.assertEqual(m["observation_rows"],
                         m["conditionally_observable_rows"] + sum(
                             1 for row in self._read_forward()
                             if row["observation_status"] != "可前瞻觀察_仍需來源核實"))
        self.assertSetEqual(set(m["matured_observation_rows_without_verified_returns"]),
                            {"10", "20", "60"})
    def _read_forward(self):
        import csv
        with (DATA / "forward_observation.csv").open(encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    def _fixture(self, folder):
        names = ["research_snapshot_30d.json", "forward_observation_meta.json",
                 "forward_observation.csv", "research_readiness_meta.json",
                 "corporate_action_readiness_meta_30e.json"]
        manifest = json.loads((DATA/names[0]).read_text(encoding="utf-8"))
        names += [manifest["sources"][key]["path"].split("/")[-1] for key in REQUIRED]
        p = Path(folder)
        for name in names:
            shutil.copy2(DATA / name, p / name)
        return p
    def test_rejects_tampered_csv_even_with_unchanged_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fixture(tmp)
            target = data/"chip_signals.csv"
            target.write_bytes(target.read_bytes()+b"\n")
            with self.assertRaisesRegex(ValueError, "Source bytes differ"):
                audit(data)
    def test_rejects_inconsistent_observation_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fixture(tmp)
            path = data/"forward_observation_meta.json"
            m = json.loads(path.read_text(encoding="utf-8"))
            m["observation_rows_all_cohorts"] += 1
            path.write_text(json.dumps(m), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "counts conflict"):
                audit(data)
    def test_rejects_legacy_gate_claiming_metrics_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fixture(tmp)
            path = data/"research_readiness_meta.json"
            m = json.loads(path.read_text(encoding="utf-8"))
            m["performance_metrics_enabled"] = True
            path.write_text(json.dumps(m), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "legacy performance gate"):
                audit(data)
    def test_report_contains_no_numeric_win_probability(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._fixture(tmp)
            m = write_report(data)
            stored = json.loads((data/"prediction_readiness_30f.json").read_text(encoding="utf-8"))
            self.assertEqual(m, stored)
            self.assertNotIn("predicted_win_rate", stored)
            self.assertNotIn("prediction_probability", stored)
            self.assertTrue(stored["protocol"]["no_estimate_if_unverified"])

if __name__ == "__main__":
    unittest.main()
