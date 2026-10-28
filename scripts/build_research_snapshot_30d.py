#!/usr/bin/env python3
"""3.0D exact-byte manifests of the eight published research data tables.

This is a deployment-integrity receipt, NOT historical release-time proof.
The manifest is generated after daily CSV updates and before Pages upload.
"""
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCES={
    "factor":("factor_evidence_29a.csv","price_asof"),
    "chip":("chip_signals.csv","flow_asof"),
    "tech":("tech_crosscheck.csv","price_asof"),
    "industry":("industry_relative_28c.csv","asof"),
    "risk":("risk_observations_28d.csv","price_asof"),
    "valuation":("f2_valuation_29e.csv","asof"),
    "revenue":("revenue_snapshot_28c.csv","table_date"),
    "publication":("publication_gate_29o.csv","price_asof"),
}
STOCK_RE=re.compile(r"^[0-9]{4,6}$")
DAY_RE=re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
def valid_day(value):
    if not DAY_RE.fullmatch(value or ""):return False
    try:dt.date.fromisoformat(value)
    except ValueError:return False
    return True
def describe(raw, filename, date_field):
    text=raw.decode("utf-8-sig")
    rows=list(csv.DictReader(io.StringIO(text,newline="")))
    if not rows and not text.strip():raise ValueError(f"{filename}: empty source")
    reader=csv.DictReader(io.StringIO(text,newline=""))
    headers=reader.fieldnames or []
    for required in ("stock_id",date_field):
        if required not in headers:raise ValueError(f"{filename}: missing {required}")
    ids=[(r.get("stock_id") or "").strip() for r in rows]
    nonempty=[v for v in ids if v]
    if len(set(nonempty))!=len(nonempty):
        raise ValueError(f"{filename}: duplicated stock_id")
    invalid=[v for v in ids if not STOCK_RE.fullmatch(v)]
    if invalid:raise ValueError(f"{filename}: invalid stock id, first {invalid[0]!r}")
    dates=[(r.get(date_field) or "").strip() for r in rows]
    bad=[x for x in dates if x and not valid_day(x)]
    if bad:raise ValueError(f"{filename}: invalid {date_field} value {bad[0]!r}")
    good=[x for x in dates if valid_day(x)]
    return {
        "path":"data/"+filename,
        "sha256":hashlib.sha256(raw).hexdigest(),
        "byte_length":len(raw),
        "row_count":len(rows),
        "unique_stock_count":len(nonempty),
        "asof_field":date_field,
        "asof_min":min(good) if good else "",
        "asof_max":max(good) if good else "",
        "asof_missing":len(rows)-len(good),
    }
def build(root=ROOT,clock=None):
    now=clock or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:raise ValueError("generation time must have timezone")
    now=now.astimezone(dt.timezone.utc)
    site=root/"site"
    tables={}
    for key,(filename,date_col) in SOURCES.items():
        path=site/"data"/filename
        if not path.is_file():raise FileNotFoundError(f"required published research source missing: {path}")
        tables[key]=describe(path.read_bytes(),filename,date_col)
    if tables["factor"]["row_count"]<1000:raise ValueError("research universe unexpectedly small")
    manifest={
        "schema_version":"3.0D",
        "assembled_at_utc":now.isoformat(timespec="seconds"),
        "verification_scope":"Exact bytes of eight CSV tables included in this GitHub Pages deployment",
        "data_is_not_historical_publication_proof":True,
        "formal_model_scoring_enabled":False,
        "performance_probabilities_enabled":False,
        "snapshot_source_count":len(tables),
        "sources":tables,
    }
    (site/"data"/"research_snapshot_30d.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return manifest
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--verify-only",action="store_true",
                        help="Check manifest against actual exact bytes; do not regenerate.")
    args=parser.parse_args()
    if args.verify_only:
        site=ROOT/"site"
        stored=json.loads((site/"data"/"research_snapshot_30d.json").read_text(encoding="utf-8"))
        assert stored["snapshot_source_count"]==len(SOURCES)
        for key,(filename,col) in SOURCES.items():
            actual=describe((site/"data"/filename).read_bytes(),filename,col)
            assert actual==stored["sources"][key],f"snapshot file modified after manifest: {key}"
        assert not stored["formal_model_scoring_enabled"]
        assert not stored["performance_probabilities_enabled"]
        print("PASS 3.0D: 8 published research sources match exact-byte manifest")
    else:
        m=build()
        print("3.0D exact-byte research manifest generated",m["assembled_at_utc"],
              "stocks",m["sources"]["factor"]["row_count"])
