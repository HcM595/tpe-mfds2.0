"""3.0I multi-window statistics, all hypothetical observations."""
import copy
import datetime as dt
import unittest

from scripts.walk_forward_multifold_30i import evaluate_multifold
from tests.test_walk_forward_probability_lab_30f import fixture

ASOF="2027-01-01T00:00:00+00:00"

def study(samples=None, horizon=10, **kwargs):
    return evaluate_multifold(
        fixture(cohorts=85, horizon=horizon) if samples is None else samples,
        horizon, asof_utc=ASOF, **kwargs)

class MultiFoldTests(unittest.TestCase):
    def test_multiple_disjoint_out_of_time_folds(self):
        report=study()
        self.assertEqual(report["status"], "laboratory_multifold_baseline_only")
        self.assertGreaterEqual(report["completed_folds"],3)
        self.assertFalse(report["production_prediction_allowed"])
        self.assertFalse(report["individual_stock_probability_allowed"])
        self.assertFalse(report["real_evidence_independently_authenticated"])
        seen=set()
        last=None
        for fold in report["folds"]:
            self.assertLess(fold["latest_train_label_at_utc"],fold["first_signal_at_utc"])
            self.assertGreater(fold["train_rows_verified_before_signal"],0)
            self.assertGreater(fold["train_rows_purged_unavailable"],0)
            self.assertFalse(seen.intersection(fold["test_cohorts"]))
            seen.update(fold["test_cohorts"])
            if last:self.assertLess(last,fold["first_signal_at_utc"])
            last=fold["first_signal_at_utc"]
        self.assertEqual(report["tested_distinct_cohorts"],len(seen))
        self.assertEqual(report["tested_rows"],sum(f["test_n"] for f in report["folds"]))
        self.assertEqual(sum(x["samples"] for x in report["calibration_buckets"]),
                         report["tested_rows"])
        self.assertEqual(report,study())

    def test_all_three_predeclared_horizons(self):
        for horizon in (10,20,60):
            self.assertEqual(study(horizon=horizon)["horizon_sessions"],horizon)

    def test_insufficient_true_folds_is_not_reported_as_success(self):
        result=study(samples=fixture(cohorts=35))
        self.assertEqual(result["status"],"insufficient_valid_chronological_folds")
        self.assertFalse(result["production_prediction_allowed"])
        self.assertLess(result["completed_folds"],3)

    def test_training_label_not_published_at_first_holdout_signal_is_purged(self):
        samples=fixture(cohorts=85)
        baseline=study(samples)
        first=baseline["folds"][0]["first_signal_at_utc"]
        late=(dt.datetime.fromisoformat(first)+dt.timedelta(hours=1)).isoformat()
        for sample in samples:
            if sample["cohort_id"]=="cohort-015":
                sample["label_available_at_utc"]=late
        second=study(samples)
        self.assertEqual(second["status"],"laboratory_multifold_baseline_only")
        self.assertEqual(second["folds"][0]["train_rows_verified_before_signal"],
                         baseline["folds"][0]["train_rows_verified_before_signal"]-5)
        self.assertEqual(second["folds"][0]["train_rows_purged_unavailable"],
                         baseline["folds"][0]["train_rows_purged_unavailable"]+5)

    def test_holdout_outcomes_cannot_change_first_forecast(self):
        original=fixture(cohorts=85)
        base=study(original)
        changed=copy.deepcopy(original)
        first_test=set(base["folds"][0]["test_cohorts"])
        for sample in changed:
            if sample["cohort_id"] in first_test:
                sample["net_total_return"]=0.5
        comparison=study(changed)
        self.assertEqual(comparison["folds"][0]["baseline_train_probability"],
                         base["folds"][0]["baseline_train_probability"])
        self.assertNotEqual(comparison["folds"][0]["holdout_fraction_positive"],
                            base["folds"][0]["holdout_fraction_positive"])

    def test_after_asof_outcomes_and_bad_unverified_receipts_fail(self):
        rows=fixture(cohorts=85)
        rows[0]["label_available_at_utc"]="2027-02-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"after evaluation cutoff"):
            study(rows)
        rows=fixture(cohorts=85)
        rows[0]["execution_verified"]=False
        with self.assertRaisesRegex(ValueError,"Unverified"):
            study(rows)
        rows=fixture(cohorts=85)
        rows[0]["execution_receipt_sha256"]="missing"
        with self.assertRaisesRegex(ValueError,"receipt"):
            study(rows)

    def test_tied_decision_clocks_do_not_enter_different_folds(self):
        rows=fixture(cohorts=85)
        for sample in rows:
            if sample["cohort_id"]=="cohort-041":
                sample["signal_first_seen_at_utc"]=next(
                    x["signal_first_seen_at_utc"] for x in rows
                    if x["cohort_id"]=="cohort-040")
        report=study(rows)
        self.assertEqual(report["status"],"blocked_tied_cohort_decision_clocks")

    def test_configuration_rejects_shortcuts(self):
        for kw in (
            {"min_completed_folds":1}, {"test_cohorts_per_fold":1},
            {"embargo_cohorts":-1}, {"min_train_rows":0},
            {"min_train_cohorts":True},
        ):
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                study(**kw)

if __name__=="__main__":
    unittest.main()
