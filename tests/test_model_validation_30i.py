"""3.0I must never use synthetic walk-forward scores for live forecasts."""
import csv
import json
import tempfile
import unittest

from scripts.audit_model_validation_30i import evaluate_readiness, publish
from tests.test_trade_outcomes_30g import fixture_dir


class ModelGateTests(unittest.TestCase):
    def test_real_data_has_no_authenticated_probability_samples(self):
        gate=evaluate_readiness()
        self.assertEqual(gate["status"],"unverified_outcomes_block_production_model")
        self.assertEqual(gate["source_observation_rows"],387)
        self.assertFalse(gate["stock_specific_probability_enabled"])
        self.assertFalse(gate["formal_win_rate_model_enabled"])
        for key in ("10","20","60"):
            self.assertEqual(gate["per_horizon"][key]["officially_authenticated_model_labels"],0)
            self.assertEqual(gate["per_horizon"][key]["completed_out_of_time_folds"],0)

    def test_report_reproducible_without_fabricated_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=fixture_dir(tmp)
            gate=publish(path)
            publish(path,verify_only=True)
            stored=json.loads((path/"model_validation_readiness_30i.json").read_text(encoding="utf-8"))
            self.assertEqual(stored,gate)
            self.assertNotIn("predicted_win_rate",stored)
            self.assertNotIn("historical_accuracy",stored)

    def test_tampered_stored_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=fixture_dir(tmp)
            publish(path)
            output=path/"model_validation_readiness_30i.json"
            report=json.loads(output.read_text(encoding="utf-8"))
            report["formal_win_rate_model_enabled"]=True
            output.write_text(json.dumps(report),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"differs"):
                publish(path,verify_only=True)

    def test_fabricated_maturity_cannot_qualify_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=fixture_dir(tmp)
            source=path/"forward_observation.csv"
            with source.open(encoding="utf-8-sig",newline="") as f:
                records=list(csv.DictReader(f))
            records[0]["performance_status"]="回測命中率90%"
            with source.open("w",encoding="utf-8-sig",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=list(records[0]))
                writer.writeheader();writer.writerows(records)
            with self.assertRaisesRegex(ValueError,"unverified performance"):
                evaluate_readiness(path)


if __name__=="__main__":
    unittest.main()
