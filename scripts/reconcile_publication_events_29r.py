#!/usr/bin/env python3
"""2.9R: cautious material-announcement / source-version reconciliation.

Company and market must match, and title must contain explicit topic language.
A title match is only a human review candidate, NEVER proof that F2/F3/REVENUE
values were released at that time. In particular F2 P/E and P/B are price
derived ratios, not the same object as an income statement announcement.
No retroactive timestamp backfilling or scoring.
"""
import csv
import datetime as dt
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Taipei")
REVIEW_FIELDS=["stock_id","stock_name","market","price_asof","factor","evidence_key",
   "source_sha256","source_first_seen_utc","original_review_status",
   "same_company_event_count","topic_candidate_count","topic_event_keys",
   "candidate_latest_speech_at_taipei","candidate_after_price_cutoff",
   "event_and_factor_payload_identical","reconciliation_status","historical_clock_eligible",
   "release_time_verified","evidence_note"]
EVENT_FIELDS=["event_key","stock_id","stock_name","market","source_speech_day",
   "source_speech_clock","source_speech_at_taipei","event_title","event_payload_sha256",
   "observed_first_at_utc","event_subject_category","possible_factor_topic",
   "factor_release_proof","review_note"]
# Only explicit subject phrases may warrant human inspection; no fuzzy/ML
# matching, no dividend/financial-warning event promoted as a revenue release.
REVENUE_RX=re.compile(r"月營收|單月營收|合併營收|營業收入|營收數字|自結營收")
GOV_RX=re.compile(r"董事長.{0,8}(兼任|不兼任).{0,6}總經理|總經理.{0,8}(兼任|不兼任).{0,6}董事長")
FINANCIAL_RX=re.compile(r"財務報告|財報|合併財務|損益表|每股盈餘|自結損益|盈利警告")
OTHER_RX=re.compile(r"股利|配息|股票面額|更名|名稱變更|庫藏股|資產|設備|證券|取得|處分")
def read(path):
    if not path.exists():return []
    with path.open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        w.writeheader();w.writerows(rows)
def category(text):
    s=re.sub(r"\s+","","".join(str(text or "").splitlines()))
    if REVENUE_RX.search(s):return "explicit_monthly_revenue_topic","REVENUE"
    if GOV_RX.search(s):return "explicit_chair_ceo_overlap_topic","F3"
    if FINANCIAL_RX.search(s):return "general_financial_statement_topic",""
    if OTHER_RX.search(s):return "other_corporate_disclosure",""
    return "unclassified_material_event",""
def event_timestamp(text):
    if not text:return None
    try:
        t=dt.datetime.fromisoformat(text)
        return t.astimezone(dt.timezone.utc) if t.tzinfo else None
    except (TypeError,ValueError):return None
def price_cutoff(text):
    try:
        d=dt.date.fromisoformat(text)
        return dt.datetime.combine(d,dt.time.min,TZ).astimezone(dt.timezone.utc) if d.isoformat()==text else None
    except (ValueError,TypeError):return None
def index_review(rows):
    seen={}
    for r in rows:
        sid=r.get("stock_id","")
        market=r.get("market","")
        factor=r.get("factor","")
        if not sid or market not in ("上市","上櫃") or factor not in ("F2","F3","REVENUE"):
            raise ValueError("invalid publication review record")
        key=(sid,market,factor)
        if key in seen:raise ValueError("duplicate factor review entry: "+str(key))
        seen[key]=r
    return seen
def build(root=ROOT):
    data=root/"site"/"data"
    reviews=read(data/"publication_review_queue_29p.csv")
    if not reviews:raise ValueError("2.9P publication review file missing or empty")
    master=index_review(reviews)
    events=read(data/"material_events_29q.csv")
    by_company=defaultdict(list)
    event_rows=[]
    seen_events=set()
    for ev in events:
        key=ev.get("event_key","")
        if not key or key in seen_events:raise ValueError("missing or duplicated official material event key")
        seen_events.add(key)
        sid,market=ev.get("stock_id",""),ev.get("market","")
        if not sid or market not in ("上市","上櫃"):raise ValueError("material event security identity invalid")
        label,possible_factor=category(ev.get("event_title",""))
        # Even if topic is explicit, the value is not present/confirmed and
        # first-publication time has not been independently established.
        source=ev.get("source_payload_sha256","")
        event_rows.append(dict(event_key=key,stock_id=sid,stock_name=ev.get("stock_name",""),
          market=market,source_speech_day=ev.get("source_speech_day",""),
          source_speech_clock=ev.get("source_speech_clock",""),
          source_speech_at_taipei=ev.get("source_speech_at_taipei",""),
          event_title=ev.get("event_title",""),event_payload_sha256=source,
          observed_first_at_utc=ev.get("observed_first_at_utc",""),
          event_subject_category=label,possible_factor_topic=possible_factor,
          factor_release_proof="false",
          review_note="僅重大訊息主旨文字相似；非逐公司財務來源版本首次公布或數值一致性證明"))
        by_company[(sid,market)].append((ev,label,possible_factor))
    out=[]
    categories=Counter(r["event_subject_category"] for r in event_rows)
    candidates=0
    conflicts=0
    for (sid,market,factor),row in sorted(master.items(),key=lambda x:(x[0][1],x[0][0],x[0][2])):
        same=by_company.get((sid,market),[])
        # F2 financial ratios have no direct material-announcement match,
        # even if earnings or financial statements appear in the title.
        plausible=[ev for ev,topic,pf in same if pf==factor and factor!="F2"]
        plausible.sort(key=lambda e:(e.get("source_speech_at_taipei",""),e.get("event_key","")))
        dates=[event_timestamp(ev.get("source_speech_at_taipei","")) for ev in plausible]
        cut=price_cutoff(row.get("price_asof",""))
        future=bool(cut is not None and any(t is not None and t>=cut for t in dates))
        conflicts+=int(future)
        latest=plausible[-1].get("source_speech_at_taipei","") if plausible else ""
        # A match never changes historical authorization. Even an exact date
        # and subject text is insufficient to match the original raw value.
        result=dict(stock_id=sid,stock_name=row.get("stock_name",""),
            market=market,price_asof=row.get("price_asof",""),factor=factor,
            evidence_key=row.get("evidence_key",""),source_sha256=row.get("source_sha256",""),
            source_first_seen_utc=row.get("source_first_seen_utc",""),
            original_review_status=row.get("review_status",""),
            same_company_event_count=str(len(same)),
            topic_candidate_count=str(len(plausible)),
            topic_event_keys=";".join(ev["event_key"] for ev in plausible),
            candidate_latest_speech_at_taipei=latest,
            candidate_after_price_cutoff=str(future).lower(),
            event_and_factor_payload_identical="false",
            reconciliation_status="topic_candidate_only" if plausible else ("same_company_only_unrelated_subject" if same else "no_company_event"),
            historical_clock_eligible="false",release_time_verified="false",
            evidence_note="主旨僅提供題材候選，不得對應數值及首次公布時間；需獨立逐筆審核來源正文、報表期間與原始版本")
        out.append(result)
        candidates+=len(plausible)
    event_rows.sort(key=lambda x:(x["market"],x["stock_id"],x["source_speech_at_taipei"],x["event_key"]))
    write(data/"publication_event_links_29r.csv",REVIEW_FIELDS,out)
    write(data/"material_event_topics_29r.csv",EVENT_FIELDS,event_rows)
    meta={
      "version":"2.9R","reviewed_factor_rows":len(out),"unique_stocks":len({(r["stock_id"],r["market"]) for r in out}),
      "archived_events":len(event_rows),"subject_categories":dict(categories),
      "subject_only_candidate_links":candidates,
      "candidate_rows_after_price_cutoff":conflicts,
      "verified_event_to_factor_value_links":0,
      "official_first_publication_verified":0,
      "historical_factor_eligible":0,
      "model_scoring_enabled":False,"performance_probabilities_enabled":False,
      "reconciliation_policy":"Same company+market and explicit subject hints only; F2 quote ratios have no automatic event connection. Candidate ≠ value equivalence ≠ official publication certification.",
      "next_evidence_needed":["specific event source body","source reporting period","raw filing value/hash match","independent official release proof","original source first capture before historical cutoff"]
    }
    (data/"publication_event_links_meta_29r.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out,event_rows,meta
if __name__=="__main__":
    rows,events,meta=build()
    print("2.9R reconciled",len(rows),"factor rows",len(events),"events, subject-only links",meta["subject_only_candidate_links"],"verified 0")
