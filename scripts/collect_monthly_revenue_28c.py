#!/usr/bin/env python3
"""2.8C: archival-only TWSE/TPEx monthly revenue observations.

A table release date is not a per-company filing timestamp. NEVER use the
revenue period as a historical knowledge date; revenue data in this module
cannot feed point-in-time factor scores or backtest returns.
"""
import csv
import datetime as dt
import hashlib
import json
import math
import re
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parents[1]
SOURCES = {
    "上市": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    "上櫃": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
}
HEADERS = ["stock_id","stock_name","market","industry","revenue_period","table_date",
           "month_revenue_thousand_twd","month_revenue_yoy_pct","month_revenue_mom_pct",
           "source_url","source_sha256","first_seen_utc","disclosure_time_verified"]
FIELDS = {
    "stock_id": "公司代號", "stock_name": "公司名稱", "industry": "產業別",
    "period": "資料年月", "table_date": "出表日期",
    "revenue": "營業收入-當月營收", "yoy": "營業收入-去年同月增減(%)",
    "mom": "營業收入-上月比較增減(%)",
}

def numeric(v):
    if v is None or str(v).strip() in ("", "-", "--", "N/A"):
        return None
    try:
        x=float(str(v).replace(",","").replace("%","").strip())
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):
        return None

def iso_month(v):
    s=re.sub(r"[^0-9]","",str(v))
    if len(s)==5: y,m=int(s[:3])+1911,int(s[3:])
    elif len(s)==6: y,m=int(s[:4]),int(s[4:])
    else:return None
    if not (2000<=y<=2100 and 1<=m<=12):return None
    return f"{y:04d}-{m:02d}"

def iso_date(v):
    s=re.sub(r"[^0-9]","",str(v))
    if len(s)==7: y,rest=int(s[:3])+1911,s[3:]
    elif len(s)==8: y,rest=int(s[:4]),s[4:]
    else:return None
    try:return dt.date(y,int(rest[:2]),int(rest[2:])).isoformat()
    except ValueError:return None

def parse_source(rows, market, master, sha, first_seen, now_date=None):
    if not isinstance(rows,list) or not rows or not all(isinstance(r,dict) for r in rows[:10]):
        raise ValueError("API response is not a nonempty list of records")
    if not set(FIELDS.values()).issubset(set(rows[0])):
        raise ValueError("API fields incomplete: "+",".join(sorted(set(FIELDS.values())-set(rows[0]))))
    now_date=now_date or dt.date.today()
    output=[]
    seen=set()
    skipped=Counter()
    for r in rows:
        code=str(r.get(FIELDS["stock_id"],"")).strip()
        if code not in master or master[code].get("market")!=market:
            skipped["not_in_market_master"]+=1
            continue
        period=iso_month(r.get(FIELDS["period"],""))
        release=iso_date(r.get(FIELDS["table_date"],""))
        revenue=numeric(r.get(FIELDS["revenue"]))
        yoy=numeric(r.get(FIELDS["yoy"]))
        mom=numeric(r.get(FIELDS["mom"]))
        if not period or not release or revenue is None or revenue<0:
            skipped["invalid_period_release_or_revenue"]+=1
            continue
        if period>now_date.strftime("%Y-%m") or release>now_date.isoformat():
            skipped["future_date"]+=1
            continue
        key=(code,period)
        if key in seen:
            skipped["duplicate_stock_period"]+=1
            continue
        seen.add(key)
        output.append(dict(stock_id=code,stock_name=r.get(FIELDS["stock_name"],""),
                           market=market,industry=r.get(FIELDS["industry"],""),
                           revenue_period=period,table_date=release,
                           month_revenue_thousand_twd=int(revenue) if revenue.is_integer() else revenue,
                           month_revenue_yoy_pct="" if yoy is None else round(yoy,4),
                           month_revenue_mom_pct="" if mom is None else round(mom,4),
                           source_url=SOURCES[market],source_sha256=sha,first_seen_utc=first_seen,
                           disclosure_time_verified="false"))
    if len(output)<10:
        raise ValueError("valid records unexpectedly sparse: "+str(len(output)))
    output.sort(key=lambda r:r["stock_id"])
    return output,dict(skipped)

def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as fp:
        return list(csv.DictReader(fp))

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"TPE-MFDS-research-archiver/2.8C","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=35) as f:
        raw=f.read(16_000_001)
    if len(raw)>16_000_000:
        raise ValueError("payload too large")
    return raw, json.loads(raw.decode("utf-8-sig"))

def write_csv(path,records):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=HEADERS,lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)

def collect(base=BASE,fetcher=fetch,clock=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    site=base/"site"/"data"
    archive=base/"history_data"/"revenue_sources"
    master={r["stock_id"]:r for r in read_csv(base/"history_data"/"ordinary_stock_master.csv")}
    existing_file=site/"revenue_snapshot_28c.csv"
    previous=read_csv(existing_file) if existing_file.exists() else []
    by_market={m:[dict(r) for r in previous if r.get("market")==m] for m in SOURCES}
    statuses={}
    for market,url in SOURCES.items():
        try:
            raw,data=fetcher(url)
            sha=hashlib.sha256(raw).hexdigest()
            source_path=archive/market/(sha+".json")
            if source_path.exists():
                # Keep a stable conservative date for existing identical archive;
                # do not falsely represent today's poll as the original first sight.
                info_path=archive/market/(sha+".first_seen")
                first_seen=info_path.read_text(encoding="utf-8").strip() if info_path.exists() else ""
            else:
                first_seen=clock.isoformat(timespec="seconds")
            parsed,skips=parse_source(data,market,master,sha,first_seen,clock.date())
            source_path.parent.mkdir(parents=True,exist_ok=True)
            if not source_path.exists():
                source_path.write_bytes(raw)
                (archive/market/(sha+".first_seen")).write_text(first_seen+"\n",encoding="utf-8")
            by_market[market]=parsed
            statuses[market]={"status":"ok","rows":len(parsed),"source_hash":sha,
                              "latest_period":max(r["revenue_period"] for r in parsed),
                              "source":url,"excluded":skips}
        except (OSError,ValueError,TypeError,UnicodeError,KeyError) as error:
            statuses[market]={"status":"stale_backup" if by_market[market] else "unavailable",
                              "rows":len(by_market[market]),"source":url,
                              "reason":str(error)[:250]}
    combined=sorted((r for part in by_market.values() for r in part),key=lambda r:(r["market"],r["stock_id"]))
    # If both markets fail, retain last validated file untouched instead of
    # silently overwriting with a header-only fake "success".
    if combined:
        write_csv(existing_file,combined)
    meta={"version":"2.8C","generated_at_taipei":clock.astimezone(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
          "total_rows":len(combined),"markets":statuses,
          "revenue_unit":"新台幣千元；不得直接當作元","coverage":"官方最新月份快照，並非完整歷史序列",
          "table_date_not_filing_date":True,"per_stock_publication_time_verified":False,
          "factor_F1_completed":False,"probability_enabled":False,
          "note":"出表日期是表格日期，非逐公司實際公告時間。不能把月份當知悉日，不能用於點時回測或F1盈利品質綜合分數。"}
    site.mkdir(parents=True,exist_ok=True)
    (site/"revenue_meta_28c.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return combined,meta

if __name__=="__main__":
    rows,m=collect()
    print("2.8C revenue snapshots",len(rows), {k:v["status"] for k,v in m["markets"].items()})
