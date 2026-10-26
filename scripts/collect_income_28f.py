#!/usr/bin/env python3
"""2.8F: official income statement observations (general business only).

Source table's publication date is NOT a per-company filing timestamp.
'本期淨利' might be cumulative YTD according to statement semantics; neither
quarter-only profit nor a cash-flow-to-net-income ratio is inferred here.
Never feed snapshots into point-in-time backtests without separate validation.
"""
import csv
import datetime as dt
import hashlib
import json
import math
import re
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).resolve().parents[1]
SOURCES={
    "上市":"https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
    "上櫃":"https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci",
}
COLUMNS=["stock_id","stock_name","market","fiscal_year","fiscal_quarter",
         "report_period","table_date","net_profit_source_value",
         "net_profit_source_field","amount_unit_verified","statement_basis_verified",
         "operating_cashflow_source_value","cashflow_netincome_ratio",
         "per_company_filing_time_verified","first_seen_utc","source_url","source_sha256","observation_status"]
REPORT_KEYS=("本期淨利淨損","本期稅後淨利淨損")
REQUIRED=("公司代號","公司名稱","年度","季別","出表日期")

def normalize_key(v):
    return re.sub(r"[\s()（）【】\[\]・,，：:、\u3000]+","",
                  unicodedata.normalize("NFKC",str(v or "")).replace("－","-"))

def normalize_row(row):
    return {normalize_key(k):v for k,v in row.items()}

def number(x):
    if x is None or str(x).strip() in ("","-","--","N/A","NA"):return None
    try:
        n=float(str(x).replace(",","").strip())
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None

def parse_year(value):
    s=str(value).strip()
    if not s.isdigit(): return None
    n=int(s)
    y=n+1911 if n<1911 else n
    return y if 2000<=y<=2100 else None

def parse_quarter(value):
    s=str(value).strip().replace("第","").replace("季","").replace("Q","").replace("q","")
    if not s.isdigit():return None
    n=int(s)
    return n if 1<=n<=4 else None

def parse_date(v):
    digits=re.sub(r"[^0-9]","",str(v or ""))
    if len(digits)==7: y=int(digits[:3])+1911;md=digits[3:]
    elif len(digits)==8: y=int(digits[:4]);md=digits[4:]
    else:return None
    try:return dt.date(y,int(md[:2]),int(md[2:])).isoformat()
    except ValueError:return None

def parse_rows(raw_rows,market,master,sha,first_seen,now=None):
    if not isinstance(raw_rows,list) or not raw_rows or not isinstance(raw_rows[0],dict):
        raise ValueError("income API: expected array of objects")
    fieldnames=set(normalize_row(raw_rows[0]).keys())
    if not set(REQUIRED).issubset(fieldnames):
        raise ValueError("income API: missing required columns "+str(sorted(set(REQUIRED)-fieldnames)))
    available_fields=[x for x in REPORT_KEYS if x in fieldnames]
    if not available_fields:raise ValueError("income API: current profit field missing")
    today=now or dt.date.today()
    best={}
    issues=Counter()
    for raw in raw_rows:
        row=normalize_row(raw)
        sid=str(row.get("公司代號","")).strip()
        if not re.fullmatch(r"\d{4,6}",sid) or master.get(sid,{}).get("market")!=market:
            issues["outside_company_master_or_market"]+=1
            continue
        year=parse_year(row.get("年度",""))
        quarter=parse_quarter(row.get("季別",""))
        table_date=parse_date(row.get("出表日期",""))
        if not year or not quarter or not table_date:
            issues["invalid_period_or_date"]+=1
            continue
        if (year,quarter)>(today.year, (today.month-1)//3+1) or table_date>today.isoformat():
            issues["future_report_or_table_date"]+=1
            continue
        profit_key=next((k for k in available_fields if number(row.get(k)) is not None),None)
        if not profit_key:
            issues["missing_net_profit"]+=1
            continue
        period=f"{year}Q{quarter}"
        record=dict(stock_id=sid,stock_name=str(row.get("公司名稱","")),
                    market=market,fiscal_year=str(year),fiscal_quarter=str(quarter),
                    report_period=period,table_date=table_date,
                    net_profit_source_value=str(row[profit_key]).strip(),
                    net_profit_source_field=profit_key,amount_unit_verified="false",
                    statement_basis_verified="false",operating_cashflow_source_value="",
                    cashflow_netincome_ratio="",per_company_filing_time_verified="false",
                    first_seen_utc=first_seen,source_url=SOURCES[market],source_sha256=sha,
                    observation_status="官方來源表格觀察；金額單位及累計口徑仍待核對")
        prior=best.get(sid)
        if prior is None or (record["report_period"],table_date)>(prior["report_period"],prior["table_date"]):
            best[sid]=record
        else:issues["duplicate_or_older_fiscal_period"]+=1
    rows=sorted(best.values(),key=lambda r:r["stock_id"])
    if len(rows)<10:raise ValueError("income source too sparse: "+str(len(rows)))
    return rows,dict(issues)

def read_csv(path):
    with path.open(encoding="utf-8-sig",newline="") as fp:return list(csv.DictReader(fp))

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"TPE-MFDS/2.8F research income statement collector","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=35) as response:
        raw=response.read(12_000_001)
    if len(raw)>12_000_000:raise ValueError("income response exceeds 12 MB")
    return raw,json.loads(raw.decode("utf-8-sig"))

def collect(base=BASE,fetcher=fetch,clock=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    site=base/"site"/"data"
    archive=base/"history_data"/"income_sources"
    master={r["stock_id"]:r for r in read_csv(base/"history_data"/"ordinary_stock_master.csv")}
    dest=site/"income_snapshot_28f.csv"
    previous=read_csv(dest) if dest.exists() else []
    keep={m:[r for r in previous if r.get("market")==m] for m in SOURCES}
    status={}
    for market,url in SOURCES.items():
        try:
            raw,items=fetcher(url)
            sha=hashlib.sha256(raw).hexdigest()
            path=archive/market/(sha+".json")
            marker=archive/market/(sha+".first_seen")
            seen=(marker.read_text(encoding="utf-8").strip() if marker.exists() else
                  clock.isoformat(timespec="seconds") if not path.exists() else "")
            rows,ignored=parse_rows(items,market,master,sha,seen,clock.date())
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                path.write_bytes(raw)
                marker.write_text(seen+"\n",encoding="utf-8")
            keep[market]=rows
            status[market]={"status":"ok","rows":len(rows),
                            "latest_period":max(x["report_period"] for x in rows),
                            "source":url,"sha256":sha,"excluded":ignored}
        except (OSError,ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError) as exc:
            status[market]={"status":"stale_backup" if keep[market] else "unavailable",
                            "rows":len(keep[market]),"source":url,
                            "reason":str(exc)[:250]}
    combined=sorted((row for m in SOURCES for row in keep[m]),key=lambda x:(x["market"],x["stock_id"]))
    site.mkdir(parents=True,exist_ok=True)
    if combined:
        with dest.open("w",encoding="utf-8",newline="") as fp:
            w=csv.DictWriter(fp,fieldnames=COLUMNS,lineterminator="\n",extrasaction="ignore")
            w.writeheader();w.writerows(combined)
    meta={"version":"2.8F","generated_at_taipei":clock.astimezone(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
          "rows":len(combined),"markets":status,"industry_coverage":"僅一般業(ci)；金融、證券、金控、保險、異業尚未串接",
          "cashflow_observed":0,"profit_currency_unit_verified":False,
          "accounting_ytd_vs_quarter_verified":False,"per_company_filing_times_verified":False,
          "f1_factor_eligible":False,"f1_cashflow_profit_ratio_enabled":False,
          "probability_enabled":False,
          "note":"僅官方最新綜合損益表之淨利來源欄位原值，單位、季累計口徑及逐公司公告時間未獨立核對。營業活動現金流尚未取得；本表不得當成盈利品質分數或回測歷史知悉資料。"}
    (site/"income_meta_28f.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return combined,meta

if __name__=="__main__":
    records,metadata=collect()
    print("2.8F income statement observations",metadata["rows"],
          {k:v["status"] for k,v in metadata["markets"].items()})
