"""3.0F laboratory: chronological, purged *conditional* hit-rate evaluation.

This module never reads daily site/CSV as trade outcomes. It accepts only an
independently prepared verification fixture, and cannot authorize a published
stock probability. Evidence receipt strings are references, NOT authentication.
"""
from __future__ import annotations
import datetime as dt
import math
import re
import random
from collections import defaultdict

HORIZONS = (10, 20, 60)
HEX = re.compile(r"^[0-9a-f]{64}$")
FLAGS = ("publication_verified", "corporate_actions_verified",
         "adjusted_total_return_verified", "execution_verified",
         "market_calendar_verified")
RECEIPTS = ("publication_receipt_sha256", "actions_receipt_sha256",
            "execution_receipt_sha256")


def instant(x):
    if not isinstance(x, str):
        raise ValueError("Expected timestamp with explicit UTC offset")
    try:
        result = dt.datetime.fromisoformat(x.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError("Invalid event timestamp") from e
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timezone-free timestamp is not admissible")
    return result.astimezone(dt.timezone.utc)


def interval(success, total, z=1.96):
    """Two-sided Wilson interval, not a guarantee about future trades."""
    if total <= 0:
        raise ValueError("No observations")
    p = success / total
    d = 1 + z*z/total
    center = (p + z*z/(2*total)) / d
    width = z*math.sqrt(p*(1-p)/total + z*z/(4*total*total))/d
    return [round(max(0., center-width), 6), round(min(1., center+width), 6)]


def cohort_bootstrap_interval(test_ids, cohorts, seed=30, draws=600):
    """Exploratory 95% cluster bootstrap over signal cohorts, not stock rows.

    Preserves within-cohort market correlation, but cannot remove cross-cohort
    market regime dependence. Only laboratory diagnostics, not live coverage.
    """
    if len(test_ids) < 2:
        raise ValueError("At least two distinct cohorts required")
    rng = random.Random(seed)
    cluster = [(sum(row[2] for row in cohorts[c]), len(cohorts[c])) for c in test_ids]
    n = len(cluster)
    draws_hit = []
    for _ in range(draws):
        drawn = [cluster[rng.randrange(n)] for _ in range(n)]
        wins = sum(x[0] for x in drawn)
        total = sum(x[1] for x in drawn)
        draws_hit.append(wins / total)
    draws_hit.sort()
    low = draws_hit[int((draws - 1) * .025)]
    high = draws_hit[int((draws - 1) * .975)]
    return [round(low, 6), round(high, 6)]


def evaluate(samples, horizon, min_train=200, min_test=60,
             min_train_cohorts=20, min_test_cohorts=10):
    """Out-of-time conditional base-rate diagnostic; NEVER per-stock forecast.

    Production must independently authenticate underlying archived sources,
    execution prices, corporate actions and official publication timestamps.
    """
    if horizon not in HORIZONS:
        raise ValueError("Only predeclared 10/20/60 horizons allowed")
    if not isinstance(samples, (list, tuple)):
        raise ValueError("Expected fixed, independently verified label rows")
    cohorts = defaultdict(list)
    per_stock = defaultdict(list)
    keys = set()
    for s in samples:
        if not isinstance(s, dict):
            raise ValueError("Invalid observation")
        if any(s.get(flag) is not True for flag in FLAGS):
            raise ValueError("Unverified evidence must not enter evaluation")
        if any(not HEX.fullmatch(str(s.get(field, ""))) for field in RECEIPTS):
            raise ValueError("Evidence receipt references missing")
        if s.get("horizon_sessions") != horizon or (
                not isinstance(s.get("entry_session_index"), int) or
                not isinstance(s.get("exit_session_index"), int) or
                s["exit_session_index"]-s["entry_session_index"] != horizon):
            raise ValueError("Horizon sessions do not match fixed exit rule")
        stock = str(s.get("stock_id", ""))
        cohort = str(s.get("cohort_id", ""))
        if not stock.isdigit() or not cohort:
            raise ValueError("Invalid stock or cohort identity")
        ident = (cohort, stock, horizon)
        if ident in keys:
            raise ValueError("Duplicated cohort/stock/horizon")
        keys.add(ident)
        publish, capture = instant(s.get("source_publication_at_utc")), instant(s.get("signal_first_seen_at_utc"))
        entry, exit_time = instant(s.get("entry_at_utc")), instant(s.get("exit_at_utc"))
        available = instant(s.get("label_available_at_utc"))
        if publish > capture or capture >= entry or exit_time <= entry or available <= exit_time:
            raise ValueError("Future publication, capture or outcome leakage; label availability must follow exit")
        value = s.get("net_total_return")
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < -1:
            raise ValueError("Missing or invalid verified net return")
        row = (entry, exit_time, int(value > 0), stock, capture, available)
        cohorts[cohort].append(row)
        per_stock[stock].append(row)
    for rows in per_stock.values():
        ordered = sorted(rows)
        for left, right in zip(ordered, ordered[1:]):
            if right[0] <= left[1]:
                raise ValueError("Same-stock observation holding windows overlap")
    # One frozen research cohort must have one first-observation clock.
    # Splitting cohorts at trade entry rather than at decision time leaks labels.
    for cohort, rows in cohorts.items():
        if len({row[4] for row in rows}) != 1:
            raise ValueError("Conflicting signal capture times within a cohort: " + cohort)
    ordered_cohorts = sorted(cohorts, key=lambda c: (cohorts[c][0][4], c))
    if len(ordered_cohorts) < min_train_cohorts + min_test_cohorts:
        return {"status": "insufficient_independent_cohorts", "cohorts": len(ordered_cohorts)}
    split = max(min_train_cohorts, int(len(ordered_cohorts)*0.75))
    if len(ordered_cohorts)-split < min_test_cohorts:
        split = len(ordered_cohorts)-min_test_cohorts
    train_ids, test_ids = ordered_cohorts[:split], ordered_cohorts[split:]
    test = [row for c in test_ids for row in cohorts[c]]
    start = min(row[4] for row in test)  # FIRST SIGNAL decision, not first fill
    if max(cohorts[c][0][4] for c in train_ids) >= start:
        return {"status": "non_separable_cohort_times"}
    # A prior trade can enter early yet its VERIFIED result become available
    # after the first holdout signal. Purge by result publication, NOT exit.
    train = [row for c in train_ids for row in cohorts[c]
             if row[4] < start and row[5] < start]
    if len(train) < min_train or len(test) < min_test:
        return {"status": "insufficient_purged_samples",
                "train_samples": len(train), "holdout_samples": len(test),
                "purged_train_samples": sum(len(cohorts[c]) for c in train_ids)-len(train)}
    train_wins = sum(r[2] for r in train)
    holdout_wins = sum(r[2] for r in test)
    p = (train_wins+1)/(len(train)+2)  # fixed Beta(1,1) shrinkage
    brier = sum((p-r[2])**2 for r in test)/len(test)
    return {
        "status": "laboratory_only_not_production_certified",
        "horizon_sessions": horizon,
        "train_n": len(train),
        "holdout_n": len(test),
        "train_cohorts": len(train_ids),
        "holdout_cohorts": len(test_ids),
        "purged_train_n": sum(len(cohorts[c]) for c in train_ids)-len(train),
        "train_conditional_estimate": round(p, 6),
        "holdout_hit_fraction": round(holdout_wins/len(test), 6),
        "holdout_wilson_95_naive_rows": interval(holdout_wins, len(test)),
        "holdout_cluster_bootstrap_95_exploratory": cohort_bootstrap_interval(test_ids, cohorts),
        "cluster_count": len(test_ids),
        "out_of_time_brier": round(brier, 6),
        "holdout_first_signal_at_utc": start.isoformat(),
        "latest_training_label_available_at_utc": max(r[5] for r in train).isoformat(),
        "holdout_calibration_bin": {
            "predicted_probability": round(p, 6),
            "observed_fraction": round(holdout_wins / len(test), 6),
            "samples": len(test),
        },
        "calibration_bins_count": 1,  # constant baseline is NOT a stock-level model
        "calibration_gap_abs": round(abs(p-holdout_wins/len(test)), 6),
        "stock_specific_probability_allowed": False,
        "note": ("This is a single chronological holdout, NOT verified live calibration. "
                 "Row-wise Wilson incorrectly assumes independent stocks. "
                 "Cluster bootstrap captures within-signal dependence only, "
                 "not correlation across market regimes or release-time authenticity."),
    }
