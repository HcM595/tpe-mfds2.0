#!/usr/bin/env python3
"""2.6B acceptance audit for the ACTUAL published CSVs (stdlib only).
Exit nonzero on publication inconsistencies; report coverage gaps separately.
"""
import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "site" / "data"
FOCUS = ("8064", "3533", "2345")
DATASETS = {
    "flow": ("institutional_trend.csv", ("date", "stock_id", "market",
             "foreign_net_shares", "trust_net_shares", "dealer_net_shares", "source"), 120),
    "holder": ("holder_trend.csv", ("date", "stock_id",
               "holder400_pct", "holder1000_pct", "source"), 26),
}
ISSUES = []


def check(condition, message):
    if not condition:
        ISSUES.append(message)


def parse_date(v, context):
    try:
        day = dt.date.fromisoformat(v)
        check(day.isoformat() == v, f"{context}: malformed date {v!r}")
        check(day <= dt.date.today(), f"{context}: date is in the future {v}")
        return day
    except (ValueError, TypeError):
        check(False, f"{context}: invalid date {v!r}")
        return None


def read_dataset(kind, name, headers, limit):
    with (ROOT / name).open(encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        check(set(headers).issubset(reader.fieldnames or []), f"{name}: headers missing")
        rows = list(reader)
    groups = defaultdict(list)
    duplicates = []
    invalid = []
    for i, row in enumerate(rows, start=2):
        sid = row.get("stock_id", "")
        date = row.get("date", "")
        context = f"{name}:{i} ({sid})"
        if not sid.isdigit() or not 4 <= len(sid) <= 6:
            invalid.append(f"{context}: invalid code")
        if parse_date(date, context) is None:
            invalid.append(f"{context}: invalid date")
        numeric_cols = headers[3:-1] if kind == "flow" else headers[2:-1]
        for key in numeric_cols:
            try:
                raw = str(row.get(key, "")).replace(",", "").strip()
                value = float(raw)
                if (not raw and not (kind == "flow" and key == "dealer_net_shares")) or (raw and not (-1e20 < value < 1e20)):
                    raise ValueError()
                if kind == "holder" and not 0 <= value <= 100:
                    raise ValueError()
            except (ValueError, TypeError):
                if not (kind == "flow" and key == "dealer_net_shares" and not str(row.get(key, "")).strip()):
                    invalid.append(f"{context}: invalid {key}={row.get(key)!r}")
        if any(prev.get("date") == date for prev in groups[sid]):
            duplicates.append(context)
        groups[sid].append(row)
    check(not invalid, f"{name}: {len(invalid)} invalid rows, samples {invalid[:3]}")
    check(not duplicates, f"{name}: {len(duplicates)} duplicated stock-dates, samples {duplicates[:3]}")
    too_many = [sid for sid, data in groups.items() if len(data) > limit]
    check(not too_many, f"{name}: >{limit} rows for {too_many[:4]}")
    return rows, groups, max((r["date"] for r in rows), default=None)


def main():
    meta = json.loads((ROOT / "chip_trend_meta.json").read_text(encoding="utf-8"))
    backfill = json.loads((ROOT / "chip_backfill_meta.json").read_text(encoding="utf-8"))
    check(meta.get("version") == "2.6B", "metadata version is not 2.6B")
    loaded = {}
    for kind, (filename, headers, limit) in DATASETS.items():
        rows, groups, latest = read_dataset(kind, filename, headers, limit)
        loaded[kind] = groups
        check(meta.get(kind + "_rows") == len(rows), f"{kind}: meta row count mismatch")
        check(meta.get(kind + "_stocks") == len(groups), f"{kind}: meta stock count mismatch")
        check(meta.get(kind + "_date_latest") == latest, f"{kind}: meta latest date mismatch")
        print(f"{kind}: rows={len(rows)} stocks={len(groups)} latest={latest} status={meta.get(kind + '_source_status')}")
    check(meta.get("historical_data_complete") is False, "do not declare historical archive complete without verification")
    dates = {}
    with (ROOT / "price_history.csv").open(encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            if row.get("stock_id") in FOCUS and row.get("date") and row.get("close"):
                dates.setdefault(row["stock_id"], set()).add(row["date"])
    # Diagnostic: compare raw archived rows to the published export for focus symbols.
    raw_path = Path(__file__).resolve().parents[1] / "history_data" / "institutional_daily.csv"
    if raw_path.is_file():
        from collections import Counter
        with raw_path.open(encoding="utf-8-sig", newline="") as fp:
            raw = [r for r in csv.DictReader(fp) if r.get("stock_id") in FOCUS]
        for sid in FOCUS:
            rr = [r for r in raw if r.get("stock_id") == sid]
            cols = ["foreign_net_shares", "trust_net_shares", "dealer_net_shares"]
            print("RAW", sid, "count", len(rr), "latest", max((x.get("date", "") for x in rr), default=None),
                  "missing_fields", dict(Counter(k for x in rr for k in cols if not str(x.get(k, "")).strip())),
                  "sample", rr[-1] if rr else None)
    report = {}
    for sid in FOCUS:
        flows = sorted(loaded["flow"].get(sid, []), key=lambda x: x["date"])
        holders = sorted(loaded["holder"].get(sid, []), key=lambda x: x["date"])
        check(len(flows) >= 2, f"{sid}: fewer than 2 valid flow observations")
        check(len(holders) >= 2, f"{sid}: fewer than 2 valid holder observations")
        flow_latest = flows[-1]["date"] if flows else None
        holder_latest = holders[-1]["date"] if holders else None
        bf = backfill.get("focus", {}).get(sid, {})
        warnings = []
        if flow_latest and bf.get("latest_flow") and flow_latest < bf["latest_flow"]:
            warnings.append(f"exported flow ends {flow_latest}, archive says {bf['latest_flow']}")
        if holder_latest and bf.get("latest_holder") and holder_latest < bf["latest_holder"]:
            warnings.append(f"exported holder ends {holder_latest}, archive says {bf['latest_holder']}")
        checks = {}
        for n in (5, 10, 20):
            date_list = sorted(d for d in dates.get(sid, set()) if flow_latest and d <= flow_latest)[-n:]
            if len(date_list) < n:
                checks[str(n)] = "insufficient_price_sessions"
            else:
                by_date = {r["date"]: r for r in flows}
                missing = [d for d in date_list if d not in by_date]
                checks[str(n)] = "missing_flow_dates:" + ",".join(missing) if missing else "available"
        report[sid] = {
            "flow_count": len(flows), "flow_latest": flow_latest,
            "holder_count": len(holders), "holder_latest": holder_latest,
            "price_sessions": len(dates.get(sid, set())),
            "flow_windows": checks, "warnings": warnings,
        }
        print(f"{sid}: {json.dumps(report[sid], ensure_ascii=False)}")
    print("RESULT: " + ("FAIL " + " | ".join(ISSUES[:12]) if ISSUES else "PASS: structural data checks"))
    if ISSUES:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
