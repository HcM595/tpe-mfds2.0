"""Controlled laboratory regression fixtures; never production probabilities."""
import copy
import datetime as dt
import unittest

from scripts.walk_forward_probability_lab_30f import evaluate, interval

UTC = dt.timezone.utc
RECEIPT = "a"*64

def fixture(cohorts=80, per_cohort=5, horizon=10):
    out=[]
    base=dt.datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(cohorts):
        entry=base+dt.timedelta(days=i*3+1)
        for j in range(per_cohort):
            out.append({
                "cohort_id": "cohort-%03d" % i,
                "stock_id": str(1000+i*per_cohort+j),
                "horizon_sessions": horizon,
                "entry_session_index": i*10,
                "exit_session_index": i*10+horizon,
                "publication_verified": True,
                "corporate_actions_verified": True,
                "adjusted_total_return_verified": True,
                "execution_verified": True,
                "market_calendar_verified": True,
                "publication_receipt_sha256": RECEIPT,
                "actions_receipt_sha256": RECEIPT,
                "execution_receipt_sha256": RECEIPT,
                "source_publication_at_utc": (entry-dt.timedelta(days=2)).isoformat(),
                "signal_first_seen_at_utc": (entry-dt.timedelta(days=1)).isoformat(),
                "entry_at_utc": entry.isoformat(),
                "exit_at_utc": (entry+dt.timedelta(days=12)).isoformat(),
                "net_total_return": 0.04 if (i+j)%3 else -0.03,
            })
    return out

class WalkForwardLabTests(unittest.TestCase):
    def test_purged_chronological_holdout_only(self):
        report=evaluate(fixture(), 10)
        self.assertEqual(report["status"], "laboratory_only_not_production_certified")
        self.assertGreaterEqual(report["train_n"], 200)
        self.assertEqual(report["holdout_n"], 100)
        self.assertGreater(report["purged_train_n"], 0)
        self.assertGreaterEqual(report["train_conditional_estimate"], 0)
        self.assertLessEqual(report["train_conditional_estimate"], 1)
        self.assertFalse(report["stock_specific_probability_allowed"])
    def test_other_predeclared_horizons(self):
        for horizon in (20, 60):
            self.assertEqual(evaluate(fixture(horizon=horizon),horizon)["horizon_sessions"],horizon)
    def test_too_few_cohorts_or_matured_labels_blocks(self):
        self.assertEqual(evaluate(fixture(cohorts=5),10)["status"],"insufficient_independent_cohorts")
        self.assertEqual(evaluate(fixture(cohorts=35,per_cohort=1),10)["status"],"insufficient_purged_samples")
    def test_no_future_information_or_unverified_evidence(self):
        for field,value in [
            ("source_publication_at_utc", "2028-01-01T00:00:00Z"),
            ("signal_first_seen_at_utc", "2028-01-01T00:00:00Z"),
            ("execution_verified", False),
            ("actions_receipt_sha256", "bad"),
            ("net_total_return", float("nan")),
            ("net_total_return", None),
            ("horizon_sessions", 60),
            ("entry_at_utc", "2026-10-27T09:00:00"),
        ]:
            rows=fixture()
            rows[0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                evaluate(rows,10)
    def test_deduplicates_and_rejects_overlapping_same_stock(self):
        rows=fixture()
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError,"Duplicated"):
            evaluate(rows,10)
        rows=fixture()
        rows[5]["stock_id"]=rows[0]["stock_id"]
        with self.assertRaisesRegex(ValueError,"overlap"):
            evaluate(rows,10)
    def test_wilson_interval_not_point_guarantee(self):
        lo,hi=interval(3,10)
        self.assertLess(lo,0.3)
        self.assertGreater(hi,0.3)
        with self.assertRaises(ValueError):
            interval(0,0)

if __name__=="__main__":
    unittest.main()
