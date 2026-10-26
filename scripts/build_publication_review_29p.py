#!/usr/bin/env python3
"""2.9P public-release evidence review queue (NOT a release-time verification).

Works only from already captured official observations. A company/date/URL
or a valid SHA256 DOES NOT establish the moment the filing was first public.
Never write a verified_publication_at_utc, a usable historical signal, or
an investment model score from these candidates.
"""
import csv
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"site"/"data"
FACTORS=("F2","F3","REVENUE")
HEAD=["stock_id","stock_name","market","price_asof","factor","evidence_key",
      "source_report_day","source_first_seen_utc","source_url","source_sha256",
      "source_status","is_official_endpoint","raw_provenance_complete",
      "verified_company_publication_utc","publication_time_verified",
      "historical_clock_eligible","review_status","blocker_codes"]
ALLOWED_HOSTS=frozenset(("openapi.twse.com.tw","www.tpex.org.tw","mopsov.twse.com.tw",
                         "mops.twse.com.tw"))
def read(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=HEAD,lineterminator="\n",extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)
def official_endpoint(url):
    try:
        u=urlsplit(str(url or ""))
        return u.scheme=="https" and (u.hostname or "").lower() in ALLOWED_HOSTS and bool(u.path.strip("/"))
    except ValueError:return False
def checksum(v):
    s=str(v or "")
    return len(s)==64 and all(x in "0123456789abcdef" for x in s)
def captured(v):
    try:
        if not v or not isinstance(v,str):return False
        t=dt.datetime.fromisoformat(v.replace("Z","+00:00"))
        return t.tzinfo is not None
    except ValueError:return False
def index(rows,label):
    d={}
    for row in rows:
        key=(row.get("stock_id",""),row.get("market",""))
        if not all(key):continue
        if key in d:raise ValueError("duplicate stock/market in "+label+": "+repr(key))
        d[key]=row
    return d
def build(root=ROOT):
    data=root/"site"/"data"
    primary=read(data/"factor_evidence_29a.csv")
    if not primary:raise ValueError("cannot build publication queue without factor evidence")
    gate=index(read(data/"publication_gate_29o.csv"),"2.9O gate")
    sources={
        "F2":index(read(data/"f2_valuation_29e.csv"),"F2 source"),
        "F3":index(read(data/"f3_governance_29e.csv"),"F3 source"),
        "REVENUE":index(read(data/"revenue_snapshot_28c.csv"),"revenue source"),
    }
    observed_keys=set()
    queue=[]
    summary=Counter()
    for base in primary:
        sid=base.get("stock_id","")
        market=base.get("market","")
        key=(sid,market)
        if not sid or market not in ("上市","上櫃") or key in observed_keys:
            raise ValueError("invalid/duplicate stock in candidate universe "+repr(key))
        observed_keys.add(key)
        g=gate.get(key,{})
        for factor in FACTORS:
            src=sources[factor].get(key,{})
            first=src.get("first_seen_utc","")
            url=src.get("source_url","")
            sha=src.get("source_sha256","")
            report=g.get(factor+"_source_report_day","")
            cutoff_pass=g.get(factor+"_asof_clock_pass","false")
            # 2.9O is authoritative for this output: discrepancies are
            # quarantined rather than silently relabeling history.
            mismatch=bool(g) and bool(g.get(factor+"_first_seen_utc")) and g[factor+"_first_seen_utc"]!=first
            blockers=set(filter(None,g.get(factor+"_blockers","").split(";")))
            if mismatch:blockers.add("archive_first_seen_disagrees_with_29o")
            if not g:blockers.add("publication_gate_missing")
            if not src:blockers.add("source_missing")
            # Monthly revenue rows are archived raw table observations without a
            # per-row source_status column. Their SHA/capture can be checked,
            # but must never imply individual-company filing verification.
            status=src.get("source_status") or ("archived_snapshot_only" if factor=="REVENUE" and src else "unavailable")
            if status=="archived_snapshot_only":blockers.add("bulk_snapshot_not_individual_filing")
            elif src and status!="ok":blockers.add("source_status_not_ok")
            if not official_endpoint(url):blockers.add("unverified_official_endpoint")
            if not checksum(sha):blockers.add("source_hash_missing_or_invalid")
            if not captured(first):blockers.add("capture_timestamp_unverified")
            # OpenAPI report-day labels never prove *individual-company*
            # publication time, even when the source URL/hash is valid.
            blockers.add("individual_company_publication_time_unverified")
            if cutoff_pass=="true":
                # Candidate queue must never silently grant eligibility,
                # even if a future upstream pipeline changes its definition.
                blockers.add("manual_evidence_review_required")
            raw_ok=(status in ("ok","archived_snapshot_only") and official_endpoint(url)
                    and checksum(sha) and captured(first) and not mismatch)
            evidence_key=hashlib.sha256(
                "|".join((market,sid,factor,sha or "no_hash")).encode("utf-8")).hexdigest()[:24]
            record=dict(stock_id=sid,stock_name=base.get("stock_name",""),
                market=market,price_asof=base.get("price_asof",""),factor=factor,
                evidence_key=evidence_key,source_report_day=report,
                source_first_seen_utc=first,source_url=url,source_sha256=sha,
                source_status=status,
                is_official_endpoint=str(official_endpoint(url)).lower(),
                raw_provenance_complete=str(bool(raw_ok)).lower(),
                verified_company_publication_utc="",publication_time_verified="false",
                historical_clock_eligible="false",review_status="awaiting_independent_publication_proof",
                blocker_codes=";".join(sorted(blockers)))
            queue.append(record)
            summary[(factor,"all")]+=1
            if raw_ok:summary[(factor,"raw_provenance_complete")]+=1
            for flag in blockers:summary[(factor,flag)]+=1
    if len(queue)!=3*len(primary):raise AssertionError("factor queue cardinality error")
    queue.sort(key=lambda r:(r["market"],r["stock_id"],FACTORS.index(r["factor"])))
    out=data/"publication_review_queue_29p.csv"
    write(out,queue)
    meta={
        "version":"2.9P",
        "universe_stocks":len(primary),
        "candidate_rows":len(queue),
        "factors":{factor:{
            "candidates":summary[(factor,"all")],
            "raw_provenance_complete":summary[(factor,"raw_provenance_complete")],
            "verified_company_release_time":0,
            "historically_usable":0,
            "blockers":{b:v for (f,b),v in summary.items()
                        if f==factor and b not in ("all","raw_provenance_complete")}
        } for factor in FACTORS},
        "model_scoring_enabled":False,
        "performance_probabilities_enabled":False,
        "strict_backtest_eligible":0,
        "evidence_rule":"OpenAPI source URL/SHA256 plus observed first_seen is archival evidence, NOT verified per-company publication time; reviewed timestamp and original event provenance must be separately established.",
        "review_policy":"All generated entries remain awaiting independent publication proof. No auto-approval, no interpolation or retroactive release-time inference.",
        "source":"2.9O publication_gate + authentic F2/F3/monthly revenue source snapshots"
    }
    (data/"publication_review_meta_29p.json").write_text(
        json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return queue,meta

if __name__=="__main__":
    queue,meta=build()
    print("2.9P review queue",len(queue),"candidates across",meta["universe_stocks"],
          "stocks; verified public release times 0; model disabled")
