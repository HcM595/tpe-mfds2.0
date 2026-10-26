#!/usr/bin/env python3
"""TPE-MFDS 2.9O: separate reporting date, first archive and verified release.

Produces conservative, per-stock F2/F3/monthly-revenue availability explanations.
This is NOT a backtest or an authorization of the original 12-factor model.
All inputs are existing archived observations; do not backfill fake publication
times from a period label, a capture timestamp, or a table's issue date.
"""
import csv
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TAIPEI=ZoneInfo("Asia/Taipei")
FACTORS=("F2","F3","REVENUE")
FIELDS=["stock_id","stock_name","market","price_asof"] + [
    prefix+"_"+col for prefix in FACTORS for col in
    ("source_report_day","first_seen_utc","verified_publication_utc",
     "asof_clock_pass","blockers")
]
def read_csv(path):
    if not path.exists(): return []
    with path.open(encoding="utf-8-sig",newline="") as fp:
        return list(csv.DictReader(fp))
def day(text):
    try:
        if not isinstance(text,str): return None
        d=dt.date.fromisoformat(text)
        return d if d.isoformat()==text else None
    except ValueError: return None
def instant(text):
    try:
        if not text or not isinstance(text,str): return None
        t=dt.datetime.fromisoformat(text.replace("Z","+00:00"))
        return t.astimezone(dt.timezone.utc) if t.tzinfo is not None else None
    except ValueError: return None
def check(price_day,report_day,first_seen,publication,authorized):
    blockers=[]
    price=day(price_day); report=day(report_day)
    if price is None:
        blockers.append("invalid_price_day")
        return False,blockers
    if report is None: blockers.append("missing_report_day")
    elif report>price: blockers.append("report_after_price_day")
    cutoff=dt.datetime.combine(price,dt.time.min,TAIPEI).astimezone(dt.timezone.utc)
    first=instant(first_seen)
    if first is None: blockers.append("first_seen_unverified")
    elif first>=cutoff: blockers.append("first_seen_after_cutoff")
    release=instant(publication)
    if release is None: blockers.append("official_publication_unverified")
    elif release>=cutoff: blockers.append("publication_after_cutoff")
    if first is not None and release is not None and release>first:
        blockers.append("capture_precedes_official_release")
    if not authorized: blockers.append("source_authorization_missing")
    return not blockers,blockers

def write_csv(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as fp:
        writer=csv.DictWriter(fp,fieldnames=FIELDS,lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)

def build(root=ROOT):
    data=root/"site"/"data"
    factors=read_csv(data/"factor_evidence_29a.csv")
    pit_rows=read_csv(data/"pit_f2f3_stock_29f.csv")
    revenues=read_csv(data/"revenue_snapshot_28c.csv")
    if not factors: raise ValueError("factor evidence master is empty")
    def index(rows,label):
        result={}
        for r in rows:
            key=(r.get("stock_id",""),r.get("market",""))
            if not all(key): continue
            if key in result: raise ValueError("duplicate stock-market in "+label+": "+repr(key))
            result[key]=r
        return result
    pit=index(pit_rows,"F2/F3 PIT")
    rev=index(revenues,"monthly revenue")
    summary={f:Counter() for f in FACTORS}
    out=[]
    for b in factors:
        key=(b.get("stock_id",""),b.get("market",""))
        if not all(key): raise ValueError("invalid factor master id or market")
        p=pit.get(key,{})
        r=rev.get(key,{})
        record={name:"" for name in FIELDS}
        record.update(stock_id=key[0],stock_name=b.get("stock_name",""),
                      market=key[1],price_asof=b.get("price_asof",""))
        for factor in ("F2","F3"):
            report=p.get(factor+"_source_report_date","")
            capture=p.get(factor+"_observed_first_at_utc","")
            release=p.get(factor+"_publication_at_utc","")
            ok,why=check(b.get("price_asof",""),report,capture,release,
                         p.get("price_asof")==b.get("price_asof") and
                         p.get(factor+"_source_status")=="ok" and
                         p.get(factor+"_usable_for_backtest")=="true")
            record.update({factor+"_source_report_day":report,
                           factor+"_first_seen_utc":capture,
                           factor+"_verified_publication_utc":release,
                           factor+"_asof_clock_pass":str(ok).lower(),
                           factor+"_blockers":";".join(why)})
            summary[factor].update(why or ["clock_only_pass"])
        report=r.get("table_date","")
        capture=r.get("first_seen_utc","")
        # A company-specific first public release is not provided by current
        # TWSE/TPEx monthly-revenue bulk tables. Always keep it absent.
        publication=r.get("verified_publication_at_utc","")
        ok,why=check(b.get("price_asof",""),report,capture,publication,
                     r.get("disclosure_time_verified")=="true" and
                     bool(r.get("source_sha256")))
        record.update(REVENUE_source_report_day=report,
                      REVENUE_first_seen_utc=capture,
                      REVENUE_verified_publication_utc=publication,
                      REVENUE_asof_clock_pass=str(ok).lower(),
                      REVENUE_blockers=";".join(why))
        summary["REVENUE"].update(why or ["clock_only_pass"])
        out.append(record)
    write_csv(data/"publication_gate_29o.csv",out)
    meta={"version":"2.9O","universe_stocks":len(out),
          "cutoff":"價格基準日 00:00 Asia/Taipei（嚴格小於）",
          "clock_gate_pass":{f:sum(x[f+"_asof_clock_pass"]=="true" for x in out) for f in FACTORS},
          "blocker_counts":{f:dict(summary[f]) for f in FACTORS},
          "model_scoring_enabled":False,"probability_enabled":False,
          "strict_backtest_eligible":0,
          "disclaimer":"時鐘門檻通過也不代表12因子已驗證；未還原價格、證券身分、樣本外研究和發佈來源仍須各自驗收。",
          "release_rule":"不得以表格出表日、月份、原始報表日或本網站首次取得時間，冒充逐公司正式公告時間。"}
    (data/"publication_gate_meta_29o.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out,meta

if __name__=="__main__":
    rows,meta=build()
    print("2.9O publication clock audit",len(rows),"stock rows; clock passes",meta["clock_gate_pass"])
