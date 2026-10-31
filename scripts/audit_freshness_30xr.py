#!/usr/bin/env python3
"""3.0X-R: conservative freshness and coverage report; does not certify trading data."""
import argparse
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data"
TZ = ZoneInfo("Asia/Taipei")

def evaluate(data=DATA, now=None):
    now = now or dt.datetime.now(TZ)
    if now.tzinfo is None:
        raise ValueError("now must be timezone aware")
    today = now.astimezone(TZ).date()
    files = {
        "official": "official_meta.json",
        "historical": "historical_evidence_meta_30q.json",
        "readiness": "research_readiness_meta.json",
        "forward": "forward_observation_meta.json",
        "coverage": "archive_coverage_meta_30r.json",
    }
    docs, errors = {}, []
    for name, path in files.items():
        try:
            docs[name] = json.loads((Path(data) / path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            errors.append(name + ": unreadable source (" + type(e).__name__ + ")")
    dates = docs.get("official", {}).get("market_dates") or {}
    current = {}
    for market in ("上市", "上櫃"):
        raw = dates.get(market)
        try:
            d = dt.date.fromisoformat(raw)
            if d > today:
                errors.append(market + ": future market date")
            current[market] = {"last_market_date": raw, "calendar_days_behind": (today - d).days}
        except (ValueError, TypeError):
            errors.append(market + ": missing/invalid market date")
    # This is a warning ONLY: exchange holidays and exceptional closures vary.
    warnings = []
    for market, item in current.items():
        if item["calendar_days_behind"] > 3:
            warnings.append(market + " last closing date is over 3 calendar days old; verify exchange calendar and pipeline")
    historical = docs.get("historical", {})
    gate = historical.get("strict_validation", {})
    verified = gate.get("verified_trade_samples", 0)
    if gate.get("model_enabled") or historical.get("first_seen_timing_certified"):
        errors.append("unexpected performance/PIT certification")
    if verified:
        errors.append("unverified trade samples must be reviewed")
    return {
        "version": "3.0X-R",
        "checked_at_taipei": now.astimezone(TZ).isoformat(),
        "status": "fail" if errors else ("review_required" if warnings else "observed"),
        "market_freshness": current,
        "historical_unique_sessions": historical.get("unique_first_captured_price_sessions"),
        "historical_observations": historical.get("stock_session_observations"),
        "verified_trade_samples": verified,
        "model_enabled": gate.get("model_enabled", False),
        "official_snapshot_version": docs.get("official", {}).get("version"),
        "historical_snapshot_version": historical.get("version"),
        "warnings": warnings,
        "errors": errors,
        "disclaimer": "Weekends, exchange holidays and exceptional closures require calendar-aware review. Not a win-rate certification.",
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="site/data/freshness_audit_30xr.json")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    result = evaluate()
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if args.strict and result["errors"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
