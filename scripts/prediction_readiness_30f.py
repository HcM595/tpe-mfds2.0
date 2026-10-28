#!/usr/bin/env python3
"""3.0F: fail-closed production win-rate eligibility report.

Never converts forward observation progress into investment outcomes. The
3.0E receipt proves byte consistency, not public availability or tradability.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
HORIZONS = (10, 20, 60)
REQUIRED = ("factor", "chip", "tech", "industry", "risk", "valuation",
            "revenue", "publication", "actions")


def document(path):
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return obj


def rows_at(path):
    with path.open(encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if not reader.fieldnames:
            raise ValueError(f"Missing CSV headers: {path.name}")
        return list(reader)


def verify_receipt(data):
    receipt = document(data / "research_snapshot_30d.json")
    if (receipt.get("schema_version") != "3.0E"
            or receipt.get("snapshot_source_count") != 9
            or receipt.get("formal_model_scoring_enabled") is not False
            or receipt.get("performance_probabilities_enabled") is not False
            or set(receipt.get("sources", {})) != set(REQUIRED)):
        raise ValueError("3.0E source receipt is missing or inconsistent")
    for key in REQUIRED:
        declared = receipt["sources"][key]
        name = declared.get("path", "")
        if not isinstance(name, str) or not name.startswith("data/") or "/" in name[5:] or ".." in name:
            raise ValueError("Unexpected source path")
        source = data / name[5:]
        raw = source.read_bytes()
        if (len(raw) != declared.get("byte_length")
                or hashlib.sha256(raw).hexdigest() != declared.get("sha256")):
            raise ValueError(f"Source bytes differ from receipt: {key}")
        records = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        if (len(records) != declared.get("row_count")
                or len({r.get("stock_id") for r in records}) != declared.get("unique_stock_count")):
            raise ValueError(f"Source row counts differ from receipt: {key}")
    return receipt


def audit(data=DATA, now=None):
    data = Path(data)
    verify_receipt(data)
    forward = document(data / "forward_observation_meta.json")
    readiness = document(data / "research_readiness_meta.json")
    actions = document(data / "corporate_action_readiness_meta_30e.json")
    observations = rows_at(data / "forward_observation.csv")
    if forward.get("version") != "2.4C" or readiness.get("version") != "2.5A" or actions.get("version") != "3.0E":
        raise ValueError("Unknown input audit version")
    if (len(observations) != forward.get("observation_rows_all_cohorts")
            or len(observations) != readiness.get("forward_observation_rows")):
        raise ValueError("Forward observation counts conflict with audit")
    if len({r["cohort_id"] for r in observations}) != forward.get("cohorts_total"):
        raise ValueError("Distinct cohort count does not match forward audit")
    if forward.get("cohorts_total") != readiness.get("cohorts_verified"):
        raise ValueError("Cohort verification mismatch")
    eligible = sum(r.get("observation_status") == "可前瞻觀察_仍需來源核實"
                   for r in observations)
    if eligible != forward.get("observation_eligible_rows_all_cohorts"):
        raise ValueError("Eligible observation count mismatch")
    if any(not str(r.get("performance_status", "")).startswith("不計算_") for r in observations):
        raise ValueError("An unverified performance label was introduced")
    matured = {}
    for horizon in HORIZONS:
        col = f"h{horizon}_status"
        if any(col not in r for r in observations):
            raise ValueError("Missing horizon status: " + col)
        matured[str(horizon)] = sum(
            r[col] == "觀察期已走完_報酬尚未驗證" for r in observations)
    strict = readiness.get("strict_performance_samples_eligible")
    if not isinstance(strict, int) or isinstance(strict, bool) or strict < 0:
        raise ValueError("Invalid strict sample eligibility")
    if strict:
        raise ValueError("A legacy eligible counter cannot certify verified outcomes")
    blockers = [
        "尚未逐筆核實可使用的歷史交易成交時間與買賣價（包含滑價及交易成本）",
        "股價未完成官方公司行動及現金股利還原，不能將原始價差當總報酬",
        "歷史因子首次觀測時間不等於官方首次公告時間，需逐筆確認當時可得性",
        "10／20／60交易日觀察進度不是已核實的交易結果與獨立樣本",
        "尚未完成同股重疊訊號去重、按時間切分與樣本外校準",
    ]
    if actions.get("historical_completeness_verified") is not False or actions.get("total_return_calculation_allowed") is not False:
        raise ValueError("Unexpected corporate-action gate; requires a new independent certification")
    if forward.get("performance_metrics_enabled") is not False or readiness.get("performance_metrics_enabled") is not False:
        raise ValueError("Unexpected legacy performance gate; requires a new independent certification")
    if not isinstance(now, dt.datetime):
        now = dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Audit clock must have UTC offset")
    return {
        "version": "3.0F",
        "generated_at_utc": now.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "status": "blocked_evidence_not_ready",
        "production_win_rate_enabled": False,
        "production_stock_probability_enabled": False,
        "verified_outcome_samples_for_model": 0,
        "observed_cohorts": forward["cohorts_total"],
        "observation_rows": len(observations),
        "conditionally_observable_rows": eligible,
        "legacy_strict_performance_samples_eligible": strict,
        "matured_observation_rows_without_verified_returns": matured,
        "previous_raw_close_mismatches": actions.get("prior_raw_close_mismatches", 0),
        "blockers": blockers,
        "protocol": {
            "horizons_trading_sessions": list(HORIZONS),
            "target": "net executable total-return > 0 after fees, taxes and slippage",
            "signal_clock": "first immutable observed timestamp, plus independently verified public release time",
            "entry": "first independently verified executable order window strictly after full signal availability",
            "exit": "predeclared executable close of each 10/20/60-session horizon",
            "corporate_actions": "independently verified distribution-adjusted returns, including suspended sessions",
            "sample_unit": "non-overlapping stock / cohort observation, purged at split boundaries",
            "validation": "chronological walk-forward with disjoint, purged out-of-sample cohorts",
            "metrics": ["out-of-sample Brier score", "calibration bins",
                        "Wilson confidence interval", "baseline comparison"],
            "no_estimate_if_unverified": True,
        },
        "disclaimer": "目前不能估計可信勝率；原始觀察、訊號分數與歷史績效不可互相代替。",
    }


def write_report(data=DATA):
    result = audit(data)
    target = Path(data) / "prediction_readiness_30f.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        actual = audit()
        stored = document(DATA / "prediction_readiness_30f.json")
        for key, val in actual.items():
            if key != "generated_at_utc" and stored.get(key) != val:
                raise ValueError("Published 3.0F evidence gate differs from verified inputs: " + key)
        print("PASS 3.0F: current evidence cannot authorize win-rate reporting")
    else:
        m = write_report()
        print("3.0F:", m["status"], "observations", m["observation_rows"],
              "verified outcomes", m["verified_outcome_samples_for_model"])
