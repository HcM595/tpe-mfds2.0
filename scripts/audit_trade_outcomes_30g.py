#!/usr/bin/env python3
"""3.0G: evidence-bound forward-outcome maturity audit (not a backtest).

The immutable origin, executable fills, shareholder distributions and market
calendar are not independently verified in the current dataset. This job
counts maturity and sources still missing; it must never infer win rates or
backfill trades from today's prices.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.prediction_readiness_30f import DATA, HORIZONS, audit as audit_30f
from scripts.prediction_readiness_30f import document, rows_at

VALID = {
    "觀察中_無績效", "等待參考交易日", "暫緩_異常待核實",
    "不列入_非有效排名", "觀察期已走完_報酬尚未驗證",
}
MATURE = "觀察期已走完_報酬尚未驗證"


def check_day(value):
    try:
        return dt.date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("Invalid observation date: " + str(value))


def inspect(data=DATA, now=None):
    """Revalidate all 3.0F inputs and enumerate fixed-horizon progress."""
    data = Path(data)
    ready = audit_30f(data, now)
    forward_path = data / "forward_observation.csv"
    raw = forward_path.read_bytes()
    observations = rows_at(forward_path)
    seen = set()
    stocks = set()
    duplicate_stock_across_cohorts = Counter()
    horizon = {}
    for n in HORIZONS:
        horizon[str(n)] = {
            "registered": len(observations), "matured_but_unverified": 0,
            "tracking": 0, "awaiting_reference": 0, "excluded": 0,
            "verified_executions": 0, "verified_total_returns": 0,
            "valid_label_samples": 0,
        }

    for row in observations:
        ident = (row.get("cohort_id"), row.get("stock_id"))
        if not all(ident) or ident in seen:
            raise ValueError("Duplicate or blank stock/cohort observation")
        seen.add(ident)
        stocks.add(row["stock_id"])
        duplicate_stock_across_cohorts[row["stock_id"]] += 1
        eligibility = row.get("observation_status")
        if eligibility not in ("可前瞻觀察_仍需來源核實",
                               "不列入_非有效排名", "暫緩_資料須核對"):
            raise ValueError("Unknown forward observation eligibility")
        reference = row.get("reference_session", "")
        reference_day = check_day(reference) if reference else None
        if reference_day and eligibility != "可前瞻觀察_仍需來源核實":
            raise ValueError("Excluded signal cannot have an entry reference")
        if not row.get("performance_status", "").startswith("不計算_"):
            raise ValueError("Synthetic or unverified performance status")
        for n in HORIZONS:
            key = str(n)
            prog = row.get(f"h{n}_observed_sessions", "")
            if not prog.isdigit() or not 0 <= int(prog) <= n:
                raise ValueError("Progress out of valid trading-session range")
            progress = int(prog)
            status = row.get(f"h{n}_status")
            target = row.get(f"h{n}_target_session", "")
            if status not in VALID:
                raise ValueError("Unknown 10/20/60-day status")
            target_day = check_day(target) if target else None
            if target_day and (reference_day is None or target_day <= reference_day):
                raise ValueError("Target must follow reference session")
            if status == MATURE:
                if target_day is None or progress != n or not reference_day:
                    raise ValueError("Mature status does not match session progress")
                horizon[key]["matured_but_unverified"] += 1
            elif status == "觀察中_無績效":
                if not reference_day or progress >= n or target_day is not None:
                    raise ValueError("Tracking reference/status inconsistency")
                horizon[key]["tracking"] += 1
            elif status == "等待參考交易日":
                if reference_day or target_day or progress:
                    raise ValueError("Waiting observation has a simulated session")
                horizon[key]["awaiting_reference"] += 1
            else:
                if progress or target_day:
                    raise ValueError("Excluded or quarantined observation has target")
                horizon[key]["excluded"] += 1
            if status in (MATURE, "觀察中_無績效") and eligibility != "可前瞻觀察_仍需來源核實":
                raise ValueError("Ineligible stock counted toward observation")
            if horizon[key]["matured_but_unverified"] > ready["observation_rows"]:
                raise ValueError("Horizon count overflow")
    if len(seen) != ready["observation_rows"]:
        raise ValueError("3.0F total vs 3.0G sample mismatch")
    for n in HORIZONS:
        key = str(n)
        if horizon[key]["matured_but_unverified"] != ready["matured_observation_rows_without_verified_returns"][key]:
            raise ValueError("3.0F maturity counters differ from raw observations")
        if sum(horizon[key][k] for k in ("matured_but_unverified", "tracking",
                                         "awaiting_reference", "excluded")) != len(seen):
            raise ValueError("Observation group totals do not add up")
    if not isinstance(now, dt.datetime):
        now = dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Generation clock must have timezone")
    return {
        "version": "3.0G",
        "generated_at_utc": now.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "status": "verified_trade_outcomes_unavailable",
        "production_prediction_allowed": False,
        "outcome_calculation_allowed": False,
        "input_forward_csv_sha256": hashlib.sha256(raw).hexdigest(),
        "cohort_count": ready["observed_cohorts"],
        "observations": len(seen),
        "stocks_ever_observed": len(stocks),
        "stocks_reappearing_in_multiple_cohorts": sum(v > 1 for v in duplicate_stock_across_cohorts.values()),
        "per_horizon": horizon,
        "required_sources": {
            "immutable_signal_and_pit_publication": "unverified",
            "official_exchange_specific_session_calendar": "unverified",
            "independently_verified_executable_entry_and_exit": "missing",
            "fees_taxes_slippage": "missing",
            "cash_stock_distributions_and_adjusted_total_return": "unverified",
            "independent_sample_split_and_calibration": "unverified",
        },
        "display_policy": "展示追蹤進度與缺口；全部已走完的觀察仍不可當成已成交樣本，禁用勝率。",
        "warning": "研究進度≠報酬；已到期≠已核實成交。禁止由原始收盤價自動補造交易結果。",
    }


def publish(data=DATA, verify_only=False):
    report = inspect(data)
    path = Path(data) / "outcome_readiness_30g.json"
    if verify_only:
        prior = document(path)
        for key, value in report.items():
            if key != "generated_at_utc" and prior.get(key) != value:
                raise ValueError("3.0G report differs from the verified source CSV")
        return report
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    opts = parser.parse_args()
    report = publish(verify_only=opts.verify_only)
    print("3.0G PASS:", report["observations"],
          "observations, verified outcomes per horizon:",
          [report["per_horizon"][str(n)]["verified_total_returns"] for n in HORIZONS],
          "publication mode blocked")
