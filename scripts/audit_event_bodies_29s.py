#!/usr/bin/env python3
"""2.9S: correlate official announcement BODIES with archived source versions.

Official material-information '說明' and '符合條款' fields can supply
human-review evidence, but NEVER establish first publication of a valuation,
governance, or revenue dataset. This script verifies immutable payload SHA256,
market+stock+event identity, source first-seen metadata and body variants.
It outputs body/period candidates but no approved release times or model scores.
"""
import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter,defaultdict
from pathlib import Path

from scripts.collect_material_events_29q import parse as event_parse, URLS, MAX_BYTES
from scripts.reconcile_publication_events_29r import category

ROOT=Path(__file__).resolve().parents[1]
FIELDS=["event_key","stock_id","stock_name","market","source_speech_at_taipei",
        "event_title","event_clause","fact_date_in_source","body_sha256",
        "body_excerpt","body_characters","body_variants_seen",
        "body_archive_status","original_payload_sha256","original_first_seen_utc",
        "candidate_topic","revenue_period_candidate","period_evidence_status",
        "related_financial_factor","financial_value_equivalence_verified",
        "independent_first_publication_verified","history_eligible",
        "review_blockers"]
MONTH=re.compile(r"(?:民國\s*)?(?P<year>\d{2,4})\s*年\s*(?P<month>0?[1-9]|1[0-2])\s*月")
def read(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore",lineterminator="\n")
        w.writeheader();w.writerows(rows)
def revenue_period_candidate(title,body):
    """Unverified text observation; never infer a filing from bare financial numbers."""
    found=set()
    for source in (title,body):
        s=" ".join(str(source or "").split())
        # Require revenue language in that component; never treat bare dates
        # from an asset or equity announcement as a reporting period.
        if not re.search(r"月營收|合併營收|營業收入",s):continue
        for m in MONTH.finditer(s):
            year,month=int(m.group("year")),int(m.group("month"))
            if year<200:year+=1911
            if 2000<=year<=2100:found.add(f"{year:04d}-{month:02d}")
    if len(found)==1:return next(iter(found)),"text_only_period_not_verified"
    if len(found)>1:return "","ambiguous_multiple_months"
    return "","reporting_period_missing"
def load_verified_archives(root,markets):
    """Re-validate archived source byte hash and first observation sidecar."""
    results=defaultdict(list)
    for market in markets:
        folder=root/"history_data"/"material_event_sources_29q"/market
        if not folder.exists():continue
        for path in sorted(folder.glob("*.json")):
            if path.stat().st_size>MAX_BYTES:raise ValueError("oversized archived source "+str(path))
            raw=path.read_bytes()
            sha=hashlib.sha256(raw).hexdigest()
            if path.stem!=sha:raise ValueError("tampered archived material source hash "+path.name)
            stamp=path.with_suffix(".first_seen")
            if not stamp.is_file():raise ValueError("archive lacks first_seen "+path.name)
            first=stamp.read_text(encoding="utf-8").strip()
            try:
                t=dt.datetime.fromisoformat(first.replace("Z","+00:00"))
                if t.tzinfo is None:raise ValueError()
            except ValueError:raise ValueError("invalid immutable first_seen "+path.name)
            data=json.loads(raw.decode("utf-8-sig"))
            if not isinstance(data,list):raise ValueError("official event archive is not array")
            key_to_row={}
            for row in data:
                if not isinstance(row,dict):continue
                # Build event key using precisely the 2.9Q identifier algorithm.
                sid=str(row.get("公司代號",row.get("SecuritiesCompanyCode",""))).strip()
                subject=str(row.get("主旨 ",row.get("主旨",row.get("Subject",""))) or "").strip()
                speech=str(row.get("發言日期",row.get("SpeechDate","")) or "").strip()
                clock=str(row.get("發言時間",row.get("SpeechTime","")) or "").strip()
                if not sid or not subject:continue
                event_key=hashlib.sha256("|".join((market,sid,speech,clock,subject)).encode("utf-8")).hexdigest()[:32]
                if event_key in key_to_row and key_to_row[event_key]!=row:
                    raise ValueError("duplicate event identity with divergent source body")
                key_to_row[event_key]=row
            for key,row in key_to_row.items():
                results[(market,key)].append((sha,first,row))
    return results
def build(root=ROOT):
    data=root/"site"/"data"
    events=read(data/"material_events_29q.csv")
    if not events: # The source may genuinely be empty; keep a header-only output.
        if not (data/"material_events_meta_29q.json").exists():
            raise ValueError("2.9Q event metadata missing")
    indexed={}
    for ev in events:
        k=(ev.get("market",""),ev.get("event_key",""))
        if k in indexed or not all(k):raise ValueError("duplicate/blank event identity")
        indexed[k]=ev
    archives=load_verified_archives(root,URLS)
    output=[];stats=Counter()
    for key,ev in sorted(indexed.items()):
        market=ev.get("market","")
        source_sha=ev.get("source_payload_sha256","")
        source_first=ev.get("observed_first_at_utc","")
        available=archives.get(key,[])
        primary=[x for x in available if x[0]==source_sha]
        matching=[x for x in primary if x[1]==source_first]
        status="original_payload_validated" if len(matching)==1 else (
            "first_seen_version_mismatch" if primary else "original_payload_not_in_archive")
        body="";clause="";fact="";bodysha=""
        variants=set()
        for _,_,record in available:
            value=str(record.get("說明","") or "")
            variants.add(hashlib.sha256(value.encode("utf-8")).hexdigest())
        if len(matching)==1:
            record=matching[0][2]
            body=str(record.get("說明","") or "")
            clause=str(record.get("符合條款","") or "")
            fact=str(record.get("事實發生日","") or "")
            bodysha=hashlib.sha256(body.encode("utf-8")).hexdigest() if body else ""
            if not body:status="original_body_absent"
        topic,factor=category(ev.get("event_title",""))
        period,period_status=revenue_period_candidate(ev.get("event_title",""),body) if factor=="REVENUE" else ("","not_applicable")
        blockers=["first_publication_time_not_verified","financial_payload_not_matched"]
        if status!="original_payload_validated":blockers.append(status)
        if len(variants)>1:blockers.append("same_event_multiple_body_versions")
        if factor=="REVENUE" and not period:blockers.append(period_status)
        output.append(dict(event_key=key[1],stock_id=ev.get("stock_id",""),
            stock_name=ev.get("stock_name",""),market=market,
            source_speech_at_taipei=ev.get("source_speech_at_taipei",""),
            event_title=ev.get("event_title",""),event_clause=clause,
            fact_date_in_source=fact,body_sha256=bodysha,
            body_excerpt=" ".join(body.split())[:500],
            body_characters=str(len(body)),body_variants_seen=str(len(variants)),
            body_archive_status=status,original_payload_sha256=source_sha,
            original_first_seen_utc=source_first,candidate_topic=topic,
            revenue_period_candidate=period,period_evidence_status=period_status,
            related_financial_factor=factor,
            financial_value_equivalence_verified="false",
            independent_first_publication_verified="false",
            history_eligible="false",review_blockers=";".join(blockers)))
        stats["body_validated"]+=int(status=="original_payload_validated")
        stats["missing_or_inconsistent"]+=int(status!="original_payload_validated")
        stats["multiple_body_variants"]+=int(len(variants)>1)
        stats["period_candidates"]+=int(bool(period))
        stats["explicit_subject_candidates"]+=int(bool(factor))
    out=data/"material_event_body_review_29s.csv"
    write(out,output)
    meta=dict(version="2.9S",archived_events=len(events),event_rows=len(output),
        original_body_validated=stats["body_validated"],
        missing_or_inconsistent=stats["missing_or_inconsistent"],
        same_event_revisions=stats["multiple_body_variants"],
        unverified_reporting_period_candidates=stats["period_candidates"],
        explicit_subject_candidates=stats["explicit_subject_candidates"],
        verified_financial_payload_equivalences=0,
        independently_verified_first_publications=0,
        historical_factor_eligible=0,model_scores_enabled=False,
        performance_probabilities_enabled=False,
        source="archived 2.9Q immutable raw JSON; event_key/company/market/source_sha/first_seen crosscheck",
        caveat="重大訊息正文及期間文字只能供人工查核；來源數值比對及首次公布證據尚未確立。")
    (data/"material_event_body_review_meta_29s.json").write_text(
        json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return output,meta
if __name__=="__main__":
    rows,meta=build()
    print("2.9S source body evidence",len(rows),"events; original raw matched",
          meta["original_body_validated"],"period candidates",
          meta["unverified_reporting_period_candidates"],"historical eligible 0")
