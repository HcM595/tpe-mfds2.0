#!/usr/bin/env python3
"""3.0I: multiple genuinely out-of-time folds for a CONSTANT baseline.

This is a synthetic/laboratory diagnostic. Receipt strings and supplied
verification booleans do NOT independently authenticate any observations.
No live individual-stock probability, performance or model approval is issued.
"""
from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict

from scripts.walk_forward_probability_lab_30f import (
    HORIZONS, instant, validated_cohorts,
)


def evaluate_multifold(
    samples, horizon, *, asof_utc,
    min_train_cohorts=20, test_cohorts_per_fold=10,
    embargo_cohorts=3, min_train_rows=80,
    min_test_rows=30, min_completed_folds=3,
):
    """Evaluate a predeclared expanding-window, cohort-blocked baseline.

    Each forecast is fixed at the FIRST SIGNAL in the fold, using only
    verified labels available STRICTLY BEFORE that signal. Test folds never
    reuse a cohort. Former holdout cohorts may enter later train windows only
    when their labels have become available, as in a real online system.
    Embargo removes recent cohorts as an additional conservative guard.
    """
    params = (min_train_cohorts, test_cohorts_per_fold, embargo_cohorts,
              min_train_rows, min_test_rows, min_completed_folds)
    if any(type(v) is not int or v < 0 for v in params):
        raise ValueError("Fold configuration must contain nonnegative integers")
    if (min_train_cohorts < 2 or test_cohorts_per_fold < 2 or
            min_completed_folds < 2 or min_train_rows < 1 or min_test_rows < 1):
        raise ValueError("Fold configuration is too small for validation")
    if horizon not in HORIZONS:
        raise ValueError("Unapproved investment holding horizon")
    cutoff = instant(asof_utc)
    cohorts, ids = validated_cohorts(samples, horizon)
    # A cohort decision cannot be divided across folds. In case independently
    # named cohorts share the same capture clock, block rather than break ties.
    clock = [cohorts[c][0][4] for c in ids]
    if len(clock) != len(set(clock)):
        return {
            "status": "blocked_tied_cohort_decision_clocks",
            "production_prediction_allowed": False,
        }
    if any(row[4] > cutoff or row[5] > cutoff for rows in cohorts.values() for row in rows):
        raise ValueError("Observation or outcome label comes from after evaluation cutoff")
    folds = []
    cursor = min_train_cohorts + embargo_cohorts
    rejected = []
    while cursor + test_cohorts_per_fold <= len(ids):
        test_ids = ids[cursor:cursor+test_cohorts_per_fold]
        first_signal = cohorts[test_ids[0]][0][4]
        train_ids = ids[:cursor-embargo_cohorts]
        eligible_train = [r for c in train_ids for r in cohorts[c]
                          if r[4] < first_signal and r[5] < first_signal]
        holdout = [r for c in test_ids for r in cohorts[c]]
        total_training = sum(len(cohorts[c]) for c in train_ids)
        if len(eligible_train) < min_train_rows or len(holdout) < min_test_rows:
            rejected.append({
                "fold_start": cursor, "reason": "insufficient_purged_samples",
                "train_n": len(eligible_train), "test_n": len(holdout),
            })
            cursor += test_cohorts_per_fold
            continue
        wins = sum(r[2] for r in eligible_train)
        p = (wins + 1) / (len(eligible_train) + 2)  # Fixed Beta(1,1), NOT fitted per stock
        brier = sum((p - r[2])**2 for r in holdout) / len(holdout)
        observed = sum(r[2] for r in holdout) / len(holdout)
        folds.append({
            "fold": len(folds) + 1,
            "first_signal_at_utc": first_signal.isoformat(),
            "latest_train_label_at_utc": max(r[5] for r in eligible_train).isoformat(),
            "test_cohorts": test_ids,
            "train_cohorts_considered": len(train_ids),
            "train_rows_verified_before_signal": len(eligible_train),
            "train_rows_purged_unavailable": total_training - len(eligible_train),
            "test_n": len(holdout),
            "test_wins": sum(r[2] for r in holdout),
            "baseline_train_probability": round(p, 8),
            "holdout_fraction_positive": round(observed, 8),
            "brier": round(brier, 8),
        })
        cursor += test_cohorts_per_fold
    if len(folds) < min_completed_folds:
        return {
            "status": "insufficient_valid_chronological_folds",
            "cohort_count": len(ids),
            "completed_folds": len(folds),
            "skipped_folds": rejected,
            "production_prediction_allowed": False,
        }
    # We aggregate only distinct holdout cohorts. Row-level scores remain
    # descriptive: shared regimes mean these are NOT independent Bernoulli bets.
    seen = set()
    total_n, total_wins, total_sq = 0, 0, 0.
    bins = defaultdict(lambda: {"n": 0, "wins": 0, "sum_prediction": 0.})
    for fold in folds:
        if any(cid in seen for cid in fold["test_cohorts"]):
            raise ValueError("Holdout cohort was evaluated more than once")
        seen.update(fold["test_cohorts"])
        n, w, p = fold["test_n"], fold["test_wins"], fold["baseline_train_probability"]
        total_n += n
        total_wins += w
        total_sq += n * fold["brier"]
        slot = min(4, int(5 * p))
        bins[slot]["n"] += n
        bins[slot]["wins"] += w
        bins[slot]["sum_prediction"] += n * p
    calibration = []
    expected_abs_error = 0.
    for i in sorted(bins):
        item = bins[i]
        n = item["n"]
        predicted = item["sum_prediction"] / n
        observed = item["wins"] / n
        expected_abs_error += (n / total_n) * abs(predicted-observed)
        calibration.append({
            "probability_bucket": i,
            "samples": n,
            "average_baseline_forecast": round(predicted, 6),
            "observed_positive_fraction": round(observed, 6),
            "warning": "One fixed climatology per fold, NOT individualized stock calibration",
        })
    avg_brier = total_sq / total_n
    return {
        "status": "laboratory_multifold_baseline_only",
        "horizon_sessions": horizon,
        "asof_utc": cutoff.isoformat(),
        "completed_folds": len(folds),
        "skipped_folds": rejected,
        "tested_distinct_cohorts": len(seen),
        "tested_rows": total_n,
        "positive_rows": total_wins,
        "pooled_baseline_brier": round(avg_brier, 6),
        "neutral_half_probability_brier": 0.25,
        "brier_improvement_over_fixed_half": round(0.25-avg_brier, 6),
        "fold_brier_range": [min(f["brier"] for f in folds),
                             max(f["brier"] for f in folds)],
        "expected_calibration_error_exploratory": round(expected_abs_error, 6),
        "calibration_buckets": calibration,
        "folds": folds,
        "production_prediction_allowed": False,
        "individual_stock_probability_allowed": False,
        "real_evidence_independently_authenticated": False,
        "warning": (
            "Multi-fold temporal scoring does not prove a stock forecasting model: "
            "the fixed historical base rate ignores stock factors, synthetic labels "
            "are not authenticated, and market-period correlation remains."
        ),
    }
