#!/usr/bin/env python3
"""2.8G: bounded, auditable MOPS cash-flow statement collection for focus stocks.

Current release: raw year-to-date cash flow from an official cash-flow table.
NOT quarter-only cashflow. Income statement period, cashflow numeric unit, and
company filing time have not all been independently verified. NO F1 ratio/score.
"""
import calendar
import csv
import datetime as dt
import hashlib
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).resolve().parents[1]
FOCUS=("8064","3533","2345","2330","2308")
NEW_STOCKS_PER_RUN=10  # bounded public-source polling; not all-market on day one
URL="https://mopsov.twse.com.tw/mops/web/ajax_t164sb05"
HEAD=["stock_id","stock_name","market","report_period","cashflow_period_start",
      "cashflow_period_end","cashflow_ytd_operating_raw","cashflow_prior_ytd_operating_raw",
      "cashflow_source_label","source_url","source_sha256","first_seen_utc","source_status",
      "amount_unit_verified","cashflow_unit","cashflow_unit_source_text","net_profit_period_basis_verified","company_filing_time_verified",
      "cashflow_netincome_ratio","factor_F1_eligible","source_caveat"]

class TableReader(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=="tr":self.row=[]
        if tag in ("td","th") and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()));self.cell=None
        if tag=="tr" and self.row is not None:
            # Real MOPS markup may close <tr> without closing the inner <th>.
            # Preserve that final header cell rather than silently discarding it.
            if self.cell is not None:
                self.row.append(" ".join(" ".join(self.cell).split()))
                self.cell=None
            self.rows.append(self.row);self.row=None

def normalized(v):
    return re.sub(r"[\s（）()\u3000－\-]","",unicodedata.normalize("NFKC",str(v or "")))

def numeric_text(v):
    s=str(v or "").strip().replace(",","")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?",s):return None
    return s

def parse_html(raw,year,quarter):
    if len(raw)>3_000_000:raise ValueError("HTML response too large")
    body=raw.decode("utf-8-sig",errors="replace")
    if body.count("\ufffd")>100:body=raw.decode("big5",errors="replace")
    rows=TableReader();rows.feed(body)
    y=year-1911
    last_month=quarter*3
    last_date=calendar.monthrange(year,last_month)[1]
    current_start=f"{y}年01月01日"
    current_end=f"{y}年{last_month:02d}月{last_date:02d}日"
    headers=[r for r in rows.rows if r and current_start in "".join(r) and current_end in "".join(r)]
    if len(headers)!=1:
        raise ValueError("exact cumulative report period header not found")
    wanted=normalized("營業活動之淨現金流入（流出）")
    hits=[r for r in rows.rows if len(r)>=3 and normalized(r[0])==wanted]
    if len(hits)!=1:raise ValueError("exact operating cash flow label missing/ambiguous")
    exact_units={normalized(x) for x in (
        "單位：新台幣仟元","單位：新臺幣仟元",
        "單位：新台幣千元","單位：新臺幣千元")}
    evidence=[cell for row in rows.rows for cell in row if normalized(cell) in exact_units]
    # A file-level unit must be present exactly once in this official statement.
    verified=len(evidence)==1
    now=numeric_text(hits[0][1]);last=numeric_text(hits[0][2])
    if now is None:raise ValueError("current-year operating cash flow missing or not numeric")
    return {"start":f"{year}-01-01","end":f"{year}-{last_month:02d}-{last_date:02d}",
            "current":now,"prior":last or "","label":hits[0][0],
            "unit_verified":verified,
            "unit":"新台幣千元" if verified else "",
            "unit_source_text":evidence[0] if verified else ""}

def read_csv(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def fetch(stock_id,year,quarter):
    form=urllib.parse.urlencode({
        "encodeURIComponent":"1","step":"1","firstin":"1","off":"1",
        "queryName":"co_id","inpuType":"co_id","TYPEK":"all","isnew":"false",
        "co_id":stock_id,"year":str(year-1911),"season":f"{quarter:02d}",
    }).encode()
    req=urllib.request.Request(URL,data=form,headers={
        "User-Agent":"Mozilla/5.0 (compatible; TPE-MFDS official cashflow research)",
        "Content-Type":"application/x-www-form-urlencoded",
        "Referer":"https://mopsov.twse.com.tw/mops/web/t164sb05",
    })
    with urllib.request.urlopen(req,timeout=35) as resp:return resp.read(3_000_001)

def collect(base=BASE,fetcher=fetch,clock=None,focus=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    site=base/"site"/"data"
    master={r["stock_id"]:r for r in read_csv(base/"history_data"/"ordinary_stock_master.csv")}
    latest_income={r["stock_id"]:r for r in read_csv(site/"income_snapshot_28f.csv")}
    dest=site/"cashflow_focus_28g.csv"
    past={r["stock_id"]:r for r in read_csv(dest)}
    archive=base/"history_data"/"cashflow_sources"
    if focus is None:
        # Always refresh priority stocks. Add up to 10 new/outdated stocks.
        pending=[sid for sid in sorted(latest_income)
                 if sid in master and sid not in FOCUS
                 and (sid not in past or
                      past[sid].get("report_period")!=latest_income[sid].get("report_period"))]
        focus=tuple(FOCUS)+tuple(pending[:NEW_STOCKS_PER_RUN])
    focus=tuple(dict.fromkeys(focus))
    result=[];statuses={}
    for sid in focus:
        inc=latest_income.get(sid)
        if not inc or not master.get(sid):
            statuses[sid]={"status":"unavailable","reason":"官方一般業淨利或公司名錄缺少"};
            if sid in past:result.append(dict(past[sid],source_status="stale_backup"))
            continue
        try:
            year=int(inc["fiscal_year"]);quarter=int(inc["fiscal_quarter"])
            if not 2000<=year<=clock.year or quarter not in (1,2,3,4):
                raise ValueError("financial quarter invalid")
            raw=fetcher(sid,year,quarter)
            parsed=parse_html(raw,year,quarter)
            sha=hashlib.sha256(raw).hexdigest()
            folder=archive/sid
            path=folder/(sha+".html")
            stamp=folder/(sha+".first_seen")
            if path.is_file():
                seen=stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else ""
            else:
                seen=clock.isoformat(timespec="seconds")
            folder.mkdir(parents=True,exist_ok=True)
            if not path.is_file():
                path.write_bytes(raw)
                stamp.write_text(seen+"\n",encoding="utf-8")
            out={k:"" for k in HEAD}
            out.update(stock_id=sid,stock_name=inc["stock_name"],market=inc["market"],
                       report_period=inc["report_period"],cashflow_period_start=parsed["start"],
                       cashflow_period_end=parsed["end"],cashflow_ytd_operating_raw=parsed["current"],
                       cashflow_prior_ytd_operating_raw=parsed["prior"],
                       cashflow_source_label=parsed["label"],source_url=URL,source_sha256=sha,
                       first_seen_utc=seen,source_status="ok",
                       amount_unit_verified="true" if parsed["unit_verified"] else "false",
                       cashflow_unit=parsed["unit"],cashflow_unit_source_text=parsed["unit_source_text"],
                       net_profit_period_basis_verified="false",
                       company_filing_time_verified="false",cashflow_netincome_ratio="",
                       factor_F1_eligible="false",
                       source_caveat=("MOPS年初累計營業活動淨現金流原值；"+
                           ("現金流單位已核對（新台幣千元），但" if parsed["unit_verified"]
                            else "現金流單位尚未核實，且")+
                           "淨利的會計口徑與公司申報時點仍未核實，不能計算F1比率"))
            result.append(out)
            statuses[sid]={"status":"ok","report_period":inc["report_period"],"sha256":sha}
        except (OSError,ValueError,TypeError,KeyError,UnicodeError) as e:
            statuses[sid]={"status":"stale_backup" if sid in past else "unavailable","reason":str(e)[:200]}
            if sid in past:result.append(dict(past[sid],source_status="stale_backup"))
        if fetcher is fetch:time.sleep(0.8)
    # Previously archived records outside today's batch remain visible,
    # explicitly marked as NOT queried in this run.
    for sid,row in sorted(past.items()):
        if sid not in focus:
            result.append(dict(row,source_status="not_checked_this_run"))
            statuses[sid]={"status":"not_checked_this_run",
                           "report_period":row.get("report_period","")}
    result.sort(key=lambda x:(x.get("market",""),x.get("stock_id","")))
    site.mkdir(parents=True,exist_ok=True)
    if result:
        with dest.open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=HEAD,lineterminator="\n",extrasaction="ignore")
            w.writeheader();w.writerows(result)
    meta={"version":"2.8H.1","generated_at_taipei":clock.astimezone(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
          "focus_stocks":list(focus),"priority_stocks":list(FOCUS),
          "batch_new_stock_cap":NEW_STOCKS_PER_RUN,
          "general_business_income_universe":len(latest_income),
          "observations":len(result),
          "unit_verified_observations":sum(1 for x in result if x.get("amount_unit_verified")=="true"),
          "fresh_unit_verified":sum(1 for x in result if x.get("source_status")=="ok"
                                    and x.get("amount_unit_verified")=="true"),
          "fresh_observations":sum(1 for x in result if x["source_status"]=="ok"),
          "per_stock":statuses,"source":"MOPS official individual cash flow HTML",
          "operating_cf_is_ytd":True,
          "source_units_checked_per_stock":True,
          "cashflow_unit":"新台幣千元（逐筆需核對官方單位欄）",
          "amount_unit_verified":False, # never grant blanket verification
          "income_accounting_basis_verified":False,"filing_timestamps_verified":False,
          "cashflow_to_netincome_ratio_enabled":False,"factor_F1_eligible":False,
          "backtest_use_enabled":False,"focus_only":True,
          "rolling_general_business_backfill":True,
          "warning":"逐股官方現金流原始單位可核對時才標註新台幣千元。淨利單位、累計會計口徑、合併範圍與申報時間尚未核對，因此不可計算現金流／淨利比率或進行點時回測；資料逐批回補，非完整全市場。"}
    (site/"cashflow_meta_28g.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result,meta

if __name__=="__main__":
    rows,meta=collect()
    print("2.8H.1 official MOPS cashflow",meta["fresh_observations"],"fresh of",len(meta["focus_stocks"]),"units checked",meta["fresh_unit_verified"])
