#!/usr/bin/env python3
"""3.0I: live-data model-readiness gate, NOT a performance report.

Lab simulations cannot authorize live probabilities. Every time this is
published, re-audit prior signed-source *consistency* checks and actual
forward horizons. Raw SHA receipts do not authenticate official timing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from scripts.audit_trade_outcomes_30g import inspect as inspect_30g
from scripts.prediction_readiness_30f import DATA, audit as audit_30f


def evaluate_readiness(data=DATA, now=None):
    data=Path(data)
    f=audit_30f(data, now=now)
    g=inspect_30g(data, now=now)
    if (f.get("production_win_rate_enabled") is not False or
        g.get("production_prediction_allowed") is not False or
        f.get("verified_outcome_samples_for_model") != 0):
        raise ValueError("Preceding research gate unexpectedly claimed probability readiness")
    horizons={}
    for horizon in (10,20,60):
        row=g.get("per_horizon", {}).get(str(horizon))
        if (not isinstance(row, dict) or row.get("valid_label_samples") != 0 or
            row.get("verified_total_returns") != 0 or
            row.get("verified_executions") != 0):
            raise ValueError("A valid model result cannot originate in the unverified observation sheet")
        horizons[str(horizon)]={
            "observation_count":row["registered"],
            "matured_unverified_count":row["matured_but_unverified"],
            "officially_authenticated_model_labels":0,
            "completed_out_of_time_folds":0,
            "published_calibration_metrics":False,
        }
    if f.get("observation_rows")!=g.get("observations"):
        raise ValueError("Observation identity differs across research gates")
    clock=now or dt.datetime.now(dt.timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("Naive audit clock forbidden")
    return {
        "version":"3.0I",
        "generated_at_utc":clock.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "status":"unverified_outcomes_block_production_model",
        "formal_win_rate_model_enabled":False,
        "stock_specific_probability_enabled":False,
        "source_cohort_count":f["observed_cohorts"],
        "source_observation_rows":f["observation_rows"],
        "per_horizon":horizons,
        "laboratory_algorithm_present":True,
        "laboratory_results_are_not_production_evidence":True,
        "gates_missing":[
            "official factor release times independently tied to each archived signal",
            "independently verified executable entry/exit and after-cost total returns",
            "completed, independent 10/20/60-day labels across multiple out-of-time folds",
            "market-regime stress, Brier skill and cohort-aware uncertainty review",
            "signed model version and permanently held-out prospective validation",
        ],
        "message":"多期回測程式已建立；真實已核實交易結果仍為零，不應顯示勝率或個股機率。",
    }


def publish(data=DATA, verify_only=False):
    report=evaluate_readiness(data)
    path=Path(data)/"model_validation_readiness_30i.json"
    if verify_only:
        if not path.is_file():raise FileNotFoundError(path)
        previous=json.loads(path.read_text(encoding="utf-8"))
        for key,val in report.items():
            if key!="generated_at_utc" and previous.get(key)!=val:
                raise ValueError("Published 3.0I report differs from verified original data")
        return report
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--verify-only",action="store_true")
    args=parser.parse_args()
    m=publish(verify_only=args.verify_only)
    print("3.0I PASS",m["source_observation_rows"],"observations; real probability disabled")
