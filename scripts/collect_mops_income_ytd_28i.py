#!/usr/bin/env python3
"""2.8I: official MOPS income YTD evidence to align with archived cashflow YTD.

Do not confuse Q2 single-quarter amount (column 1) with January-to-June YTD
amount (column 5). Audit exact source column headings and financial units.
No F1 score, cashflow/profit ratio, backtested probability or price forecasts.
"""
import calendar
import csv
import datetime as dt
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.collect_cashflow_focus_28g import TableReader, normalized, numeric_text

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"site"/"data"
URL="https://mopsov.twse.com.tw/mops/web/ajax_t164sb04"
PRIORITY=("8064","3533","2345","2330","2308")
NEW_PER_RUN=10
FIELDS=["stock_id","stock_name","market","report_period",
        "income_ytd_start","income_ytd_end","income_ytd_net_profit_raw",
        "income_prior_ytd_net_profit_raw","income_single_quarter_profit_raw",
        "amount_unit","unit_original_header","unit_verified",
        "ytd_period_verified","quarter_vs_ytd_columns_verified",
        "cashflow_report_period","cashflow_period_matched",
        "consolidation_basis_verified","per_company_filing_time_verified",
        "source_url","source_sha256","first_seen_utc","source_status",
        "net_profit_cf_ratio","factor_F1_eligible","quality_note"]
KNOWN_UNITS={normalized(x) for x in (
    "單位：新台幣仟元","單位：新臺幣仟元",
    "單位：新台幣千元","單位：新臺幣千元")}

def rows_of(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def parse_statement(raw,year,quarter):
    if len(raw)>1_500_000:raise ValueError("MOPS income HTML too large")
    body=raw.decode("utf-8-sig",errors="replace")
    if body.count("\ufffd")>100:body=raw.decode("big5",errors="replace")
    parsed=TableReader();parsed.feed(body)
    lines=parsed.rows
    roc=year-1911
    month=quarter*3
    day=calendar.monthrange(year,month)[1]
    current_q=f"{roc}年第{quarter}季"
    prev_q=f"{roc-1}年第{quarter}季"
    current_ytd=f"{roc}年01月01日至{roc}年{month:02d}月{day:02d}日"
    prior_end=calendar.monthrange(year-1,month)[1]
    prior_ytd=f"{roc-1}年01月01日至{roc-1}年{month:02d}月{prior_end:02d}日"
    heads=[r for r in lines if len(r)==5 and normalized(r[0])=="會計項目" and
           tuple(normalized(v) for v in r[1:])==
           tuple(normalized(v) for v in (current_q,prev_q,current_ytd,prior_ytd))]
    if len(heads)!=1:raise ValueError("missing exact official quarterly+YTD period header")
    subheads=[r for r in lines if len(r)==9 and
              tuple(normalized(v) for v in r[1:])==
              ("金額","%","金額","%","金額","%","金額","%")]
    if len(subheads)!=1:raise ValueError("missing official amount/percent columns")
    hits=[r for r in lines if len(r)==9 and
          normalized(r[0])==normalized("本期淨利（淨損）")]
    if len(hits)!=1:raise ValueError("missing/ambiguous total period net-income label")
    row=hits[0]
    q=numeric_text(row[1]);current=numeric_text(row[5]);prior=numeric_text(row[7])
    if current is None or q is None:raise ValueError("quarter or YTD profit not numeric")
    units=[cell for line in lines for cell in line if normalized(cell) in KNOWN_UNITS]
    verified=len(units)==1
    return {
       "quarter":q,"current":current,"prior":prior or "",
       "start":f"{year}-01-01","end":f"{year}-{month:02d}-{day:02d}",
       "unit_verified":verified,
       "unit":"新台幣千元" if verified else "",
       "unit_evidence":units[0] if verified else "",
    }

def fetch(sid,year,quarter):
    form=urllib.parse.urlencode({
        "encodeURIComponent":"1","step":"1","firstin":"1","off":"1",
        "queryName":"co_id","inpuType":"co_id","TYPEK":"all",
        "isnew":"false","co_id":sid,"year":str(year-1911),
        "season":f"{quarter:02d}"}).encode()
    req=urllib.request.Request(URL,data=form,headers={
       "User-Agent":"Mozilla/5.0 (compatible; TPE-MFDS public financial research)",
       "Content-Type":"application/x-www-form-urlencoded",
       "Referer":"https://mopsov.twse.com.tw/mops/web/t164sb04"})
    with urllib.request.urlopen(req,timeout=35) as f:
        return f.read(1_500_001)

def collect(root=ROOT,fetcher=fetch,clock=None,stocks=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    data=root/"site"/"data"
    archive=root/"history_data"/"mops_income_sources"
    cf={r["stock_id"]:r for r in rows_of(data/"cashflow_focus_28g.csv")}
    income={r["stock_id"]:r for r in rows_of(data/"income_snapshot_28f.csv")}
    dest=data/"mops_income_ytd_28i.csv"
    previous={r["stock_id"]:r for r in rows_of(dest)}
    if stocks is None:
        # Check priority list each run and at most ten more companies with
        # independently archived cashflow. Do not scrape all companies at once.
        pending=[sid for sid in sorted(cf)
                 if sid not in PRIORITY and sid in income and
                 (sid not in previous or
                  previous[sid].get("report_period")!=income[sid]["report_period"])]
        stocks=tuple(PRIORITY)+tuple(pending[:NEW_PER_RUN])
    stocks=tuple(dict.fromkeys(stocks))
    result=[];quality={}
    for sid in stocks:
        inc=income.get(sid);cash=cf.get(sid)
        if not inc or not cash:
            quality[sid]={"status":"unavailable","reason":"no archived income or cashflow"}
            if sid in previous:result.append(dict(previous[sid],source_status="stale_backup"))
            continue
        try:
            year,quarter=int(inc["fiscal_year"]),int(inc["fiscal_quarter"])
            if year<2000 or quarter not in (1,2,3,4):
                raise ValueError("invalid income period")
            last_month=quarter*3
            finish=dt.date(year,last_month,calendar.monthrange(year,last_month)[1])
            if finish>clock.astimezone(ZoneInfo("Asia/Taipei")).date():
                raise ValueError("future unfinished income quarter")
            raw=fetcher(sid,year,quarter)
            parsed=parse_statement(raw,year,quarter)
            digest=hashlib.sha256(raw).hexdigest()
            folder=archive/sid
            filename=folder/(digest+".html")
            seenfile=folder/(digest+".first_seen")
            seen=seenfile.read_text(encoding="utf-8").strip() if seenfile.is_file() else (
                clock.isoformat(timespec="seconds") if not filename.is_file() else "")
            folder.mkdir(parents=True,exist_ok=True)
            if not filename.is_file():
                filename.write_bytes(raw)
                seenfile.write_text(seen+"\n",encoding="utf-8")
            matched=(cash.get("report_period")==inc.get("report_period") and
                     cash.get("cashflow_period_start")==parsed["start"] and
                     cash.get("cashflow_period_end")==parsed["end"] and
                     cash.get("cashflow_unit")=="新台幣千元" and
                     cash.get("amount_unit_verified")=="true" and
                     parsed["unit_verified"])
            row={key:"" for key in FIELDS}
            row.update(stock_id=sid,stock_name=inc.get("stock_name",""),
                       market=inc.get("market",""),report_period=inc["report_period"],
                       income_ytd_start=parsed["start"],income_ytd_end=parsed["end"],
                       income_ytd_net_profit_raw=parsed["current"],
                       income_prior_ytd_net_profit_raw=parsed["prior"],
                       income_single_quarter_profit_raw=parsed["quarter"],
                       amount_unit=parsed["unit"],unit_original_header=parsed["unit_evidence"],
                       unit_verified="true" if parsed["unit_verified"] else "false",
                       ytd_period_verified="true",quarter_vs_ytd_columns_verified="true",
                       cashflow_report_period=cash.get("report_period",""),
                       cashflow_period_matched="true" if matched else "false",
                       consolidation_basis_verified="false",
                       per_company_filing_time_verified="false",
                       source_url=URL,source_sha256=digest,first_seen_utc=seen,
                       source_status="ok",net_profit_cf_ratio="",factor_F1_eligible="false",
                       quality_note="官方表分別呈現單季及年初累計；即使金額單位和YTD日期對齊，合併範圍及公司申報時點仍未驗證，禁止F1比率與回測")
            result.append(row)
            quality[sid]={"status":"ok","income_unit_verified":parsed["unit_verified"],
                          "period_aligned":matched}
        except (ValueError,TypeError,KeyError,OSError,UnicodeError) as exc:
            quality[sid]={"status":"stale_backup" if sid in previous else "unavailable",
                          "reason":str(exc)[:180]}
            if sid in previous:result.append(dict(previous[sid],source_status="stale_backup"))
        if fetcher is fetch:time.sleep(0.8)
    for sid,row in previous.items():
        if sid not in stocks:
            result.append(dict(row,source_status="not_checked_this_run"))
            quality[sid]={"status":"not_checked_this_run"}
    result.sort(key=lambda row:(row.get("market",""),row["stock_id"]))
    data.mkdir(parents=True,exist_ok=True)
    if result:
        with dest.open("w",encoding="utf-8",newline="") as file:
            w=csv.DictWriter(file,fieldnames=FIELDS,lineterminator="\n")
            w.writeheader();w.writerows(result)
    meta={
        "version":"2.8I","generated_at_taipei":clock.astimezone(
            ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
        "observations":len(result),"checked":len(stocks),
        "fresh_success":sum(x["source_status"]=="ok" for x in result),
        "fresh_ytd_unit_period_aligned":sum(x["source_status"]=="ok" and
                                            x["cashflow_period_matched"]=="true" for x in result),
        "income_report_ytd":"從MOPS第6欄提取當年年初累計本期淨利；第2欄為單季，不混用",
        "amount_unit":"只有逐股MOPS原始表有唯一明確新台幣仟元標頭時才核實",
        "per_stock":quality,"focus_priority":list(PRIORITY),"new_per_run":NEW_PER_RUN,
        "f1_factor_enabled":False,"cashflow_netincome_ratio_enabled":False,
        "point_in_time_backtest_enabled":False,"forecast_enabled":False,
        "missing_proof":"合併報表與個別報表基礎、個別公司申報時間、歷史各季原始封存與樣本外檢驗",
    }
    (data/"mops_income_meta_28i.json").write_text(json.dumps(
        meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result,meta

if __name__=="__main__":
    rows,meta=collect()
    print("2.8I MOPS aligned YTD income",meta["fresh_success"],
          "matched",meta["fresh_ytd_unit_period_aligned"],"of",meta["checked"])
