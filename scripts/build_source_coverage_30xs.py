#!/usr/bin/env python3
"""3.0X-S source coverage summary; descriptive only, not a performance engine."""
import json
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"site"/"data"
def build(data=DATA):
    snap=json.loads((data/"research_snapshot_30d.json").read_text(encoding="utf-8-sig"))
    hist=json.loads((data/"historical_evidence_meta_30q.json").read_text(encoding="utf-8-sig"))
    readiness=json.loads((data/"research_readiness_meta.json").read_text(encoding="utf-8-sig"))
    if snap.get("snapshot_source_count")!=9 or len(snap.get("sources",{}))!=9:
        raise ValueError("nine source declaration mismatch")
    sources=[]
    for key,entry in snap["sources"].items():
        path=entry.get("path","")
        if not path.startswith("data/") or ".." in Path(path).parts:
            raise ValueError("unsafe source path")
        rows=entry.get("row_count")
        unique=entry.get("unique_stock_count")
        missing=entry.get("asof_missing")
        if not all(isinstance(v,int) and v>=0 for v in (rows,unique,missing)):
            raise ValueError("invalid source counts")
        if unique>rows or missing>rows:
            raise ValueError("inconsistent source counts")
        sources.append(dict(key=key,path=path,rows=rows,unique_stocks=unique,
                            asof_min=entry.get("asof_min"),asof_max=entry.get("asof_max"),
                            missing_asof=missing))
    gate=hist.get("strict_validation",{})
    if snap.get("performance_probabilities_enabled") is not False or gate.get("model_enabled") is not False:
        raise ValueError("unverified probability gate unexpectedly enabled")
    if gate.get("verified_trade_samples")!=0 or readiness.get("strict_performance_samples_eligible")!=0:
        raise ValueError("performance sample assertions unexpectedly changed; audit before enabling")
    return {"version":"3.0X-S","built_at_utc":datetime.now(timezone.utc).isoformat(),
            "source_snapshot_schema":snap["schema_version"],"sources":sources,
            "historical_first_captured_sessions":hist.get("unique_first_captured_price_sessions"),
            "historical_stock_session_observations":hist.get("stock_session_observations"),
            "certified_trade_samples":0,"win_rate":None,"prediction_enabled":False,
            "interpretation":"Source row totals are not common-stock coverage or independent backtest samples.",
            "status":"descriptive_only"}
def main():
    report=build()
    out=DATA/"source_coverage_30xs.json"
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("3.0X-S source coverage:",len(report["sources"]),"source tables, formal win rate disabled")
if __name__=="__main__":main()
