#!/usr/bin/env python3
"""2.9C Official TWSE and TPEx stock-specific margin and short-sale balances.

Strictly descriptive S2 source. Official margin figures may be revised after
trading, and trade-unit definitions require independent normalization before
any cross-market calculations. Day-trading eligible lists and market totals
are NOT individual day-trading volume; neither is a proxy for retail accounts.
"""
import csv,datetime as dt,hashlib,json,math,re,urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
TWSE_ENDPOINT="https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={date}&selectType=ALL&response=json"
TPEX_ENDPOINT="https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance"
TPEX_DAYTRADE="https://www.tpex.org.tw/openapi/v1/tpex_intraday_trading_statistics"
FIELDS=["stock_id","stock_name","market","report_date","margin_previous_units","margin_balance_units","margin_change_units","short_previous_units","short_balance_units","short_change_units","margin_utilization_pct_raw","short_utilization_pct_raw","source_unit","unit_cross_market_verified","source_status","source_url","source_sha256","first_seen_utc","report_time_verified","retail_sentiment_factor_eligible","source_note"]
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS/2.9C archival-research","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=35) as r:
        raw=r.read(6_000_001)
    if len(raw)>6_000_000:raise ValueError("official response too large")
    return raw
def load(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as fp:return list(csv.DictReader(fp))
def iso(d):
    try:return dt.date.fromisoformat(str(d)).isoformat()==str(d)
    except (ValueError,TypeError):return False
def roc(raw):
    s=str(raw).strip()
    if len(s)==7 and s.isdigit():
        try:return dt.date(int(s[:3])+1911,int(s[3:5]),int(s[5:])).isoformat()
        except ValueError:return ""
    if len(s)==8 and s.isdigit():
        try:return dt.date(int(s[:4]),int(s[4:6]),int(s[6:])).isoformat()
        except ValueError:return ""
    return ""
def numeric(raw):
    s=str(raw if raw is not None else "").replace(",","").strip()
    if s in ("","-","--","N/A","NA"):return None
    if not re.fullmatch(r"-?\d+(?:\.\d+)?",s):return None
    n=float(s)
    return n if math.isfinite(n) else None
def nonnegative(raw):
    x=numeric(raw)
    return int(x) if x is not None and x>=0 and x.is_integer() else None
def percentage(raw):
    x=numeric(raw)
    return x if x is not None and 0<=x<=100 else None
def amount_record(sid,name,market,day,prev,bal,shortprev,shortbal,source,sha,first_seen,margin_util=None,short_util=None):
    vals=[nonnegative(x) for x in (prev,bal,shortprev,shortbal)]
    if any(v is None for v in vals):return None
    if not iso(day):return None
    mprev,mbal,sprev,sbal=vals
    result=dict(stock_id=sid,stock_name=str(name or ""),market=market,report_date=day,
       margin_previous_units=mprev,margin_balance_units=mbal,margin_change_units=mbal-mprev,
       short_previous_units=sprev,short_balance_units=sbal,short_change_units=sbal-sprev,
       margin_utilization_pct_raw=margin_util if margin_util is not None else "",
       short_utilization_pct_raw=short_util if short_util is not None else "",
       source_unit="官方融資融券信用交易原始單位，跨市場單位仍待核實",
       unit_cross_market_verified="false",source_status="ok",source_url=source,
       source_sha256=sha,first_seen_utc=first_seen,report_time_verified="false",
       retail_sentiment_factor_eligible="false",
       source_note="報表日期不是確認的可交易時間；信用交易餘額不是散戶投資人比例，也不是當沖成交占比")
    return result
def twse_rows(data,expected_date,master,sha,seen):
    if not isinstance(data,dict) or data.get("stat")!="OK":
        raise ValueError("TWSE dated credit statement not OK")
    day=roc(data.get("date",""))
    if not day or day!=expected_date:raise ValueError("TWSE report date differs from requested date")
    tables=data.get("tables")
    if not isinstance(tables,list):raise ValueError("TWSE response has no tables")
    found=[t for t in tables if t.get("fields")==[
        "代號","名稱","買進","賣出","現金償還","前日餘額","今日餘額",
        "次一營業日限額","買進","賣出","現券償還","前日餘額","今日餘額",
        "次一營業日限額","資券互抵","註記"]]
    if len(found)!=1:raise ValueError("TWSE stock financing table fields not recognized")
    out=[];excluded=0
    for r in found[0].get("data",[]):
        if not isinstance(r,list) or len(r)!=16:continue
        sid=str(r[0]).strip()
        if master.get(sid,{}).get("market")!="上市":continue
        record=amount_record(sid,r[1],"上市",day,r[5],r[6],r[11],r[12],
                    TWSE_ENDPOINT.format(date=day.replace("-","")),sha,seen)
        if record is None:excluded+=1
        else:out.append(record)
    if len(out)<100:raise ValueError("TWSE valid ordinary-stock margin rows too sparse")
    return out,excluded
def tpex_rows(items,master,sha,seen,today):
    required={"Date","SecuritiesCompanyCode","CompanyName",
       "MarginPurchaseBalancePreviousDay","MarginPurchaseBalance",
       "ShortSaleBalancePreviousDay","ShortSaleBalance"}
    if not isinstance(items,list) or not items or not isinstance(items[0],dict) or not required.issubset(items[0]):
        raise ValueError("TPEx financing fields not recognized")
    out=[];invalid=0
    for r in items:
        sid=str(r.get("SecuritiesCompanyCode","")).strip()
        if master.get(sid,{}).get("market")!="上櫃":continue
        day=roc(r.get("Date"))
        if not day or day>today:invalid+=1;continue
        record=amount_record(sid,r.get("CompanyName"),"上櫃",day,
            r.get("MarginPurchaseBalancePreviousDay"),r.get("MarginPurchaseBalance"),
            r.get("ShortSaleBalancePreviousDay"),r.get("ShortSaleBalance"),
            TPEX_ENDPOINT,sha,seen,
            percentage(r.get("MarginPurchaseUtilizationRate")),
            percentage(r.get("ShortSaleUtilizationRate")))
        if record is None:invalid+=1
        else:out.append(record)
    if len(out)<100:raise ValueError("TPEx valid ordinary-stock margin rows too sparse")
    return out,invalid
def archive(root,market,raw,clock):
    sha=hashlib.sha256(raw).hexdigest();directory=root/"history_data"/"s2_credit_sources"/market
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/(sha+".json");first=directory/(sha+".first_seen")
    if not target.is_file():
        target.write_bytes(raw)
        first.write_text(clock.isoformat(timespec="seconds")+"\n",encoding="utf-8")
    return sha, first.read_text(encoding="utf-8").strip() if first.is_file() else ""
def write_csv(path,rows):
    with path.open("w",encoding="utf-8",newline="") as fp:
        w=csv.DictWriter(fp,fieldnames=FIELDS,extrasaction="ignore",lineterminator="\n")
        w.writeheader();w.writerows(rows)
def collect(root=ROOT,fetch=get,clock=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    now=clock.astimezone(ZoneInfo("Asia/Taipei")).date()
    data=root/"site"/"data";data.mkdir(parents=True,exist_ok=True)
    master={r["stock_id"]:r for r in load(root/"history_data"/"ordinary_stock_master.csv")}
    official=load(data/"official_snapshot.csv")
    twse_dates=[r.get("asof") for r in official if r.get("market")=="上市" and iso(r.get("asof")) and r.get("asof")<=now.isoformat()]
    asof=max(twse_dates) if twse_dates else ""
    dest=data/"s2_credit_snapshot_29c.csv"
    past={r["stock_id"]:r for r in load(dest)}
    per_market={};records={}
    for market,url in (("上市",TWSE_ENDPOINT.format(date=asof.replace("-","")) if asof else ""),
                       ("上櫃",TPEX_ENDPOINT)):
        if not url:
            per_market[market]={"status":"unavailable","reason":"missing official dated price snapshot"}
            continue
        try:
            raw=fetch(url)
            obj=json.loads(raw.decode("utf-8-sig"))
            # Parsing first; only valid source payloads may be archived as accepted
            # stock observations. Never substitute a newer unknown report date.
            sha=hashlib.sha256(raw).hexdigest()
            seen=clock.isoformat(timespec="seconds")
            if market=="上市":
                rows,invalid=twse_rows(obj,asof,master,sha,seen)
            else:rows,invalid=tpex_rows(obj,master,sha,seen,now.isoformat())
            sha,seen=archive(root,market,raw,clock)
            for row in rows:row["first_seen_utc"]=seen
            records[market]=rows
            per_market[market]={"status":"ok","rows":len(rows),"excluded_or_missing":invalid,
                  "report_dates":sorted({r["report_date"] for r in rows}),
                  "sha256":sha,"url":url}
        except (OSError,ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as e:
            per_market[market]={"status":"stale_backup" if any(r["market"]==market for r in past.values()) else "unavailable",
                  "reason":str(e)[:180],"url":url}
    merged={}
    for sid,row in past.items():
        merged[sid]=dict(row,source_status="not_checked_this_run" if row.get("market") in records else "stale_backup")
    for market,rows in records.items():
        for row in rows:merged[row["stock_id"]]=row
    result=sorted(merged.values(),key=lambda r:(r.get("market",""),r.get("stock_id","")))
    if result:write_csv(dest,result)
    metadata={"version":"2.9C","generated_at_taipei":clock.astimezone(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
       "stocks_observed":len(result),"fresh_records":sum(r.get("source_status")=="ok" for r in result),
       "sources":per_market,
       "margin_balances_are_official_observations":True,
       "units_cross_market_verified":False,"per_stock_daytrade_volume_available":False,
       "margin_data_revisions_possible":True,"retail_account_ownership_directly_measured":False,
       "stock_sentiment_factor_verified":False,"factor_scores_enabled":False,"backtest_enabled":False,
       "probabilities_enabled":False,
       "notes":["TWSE uses dated MI_MARGN exchange table; TPEx response contains ROC report date per stock",
                "Missing credit-trading numbers are missing, never filled with zero",
                "TWSE TWTB4U is an eligible-target list, not per-stock intraday volume; TPEx intraday_trading_statistics is a market-level aggregate",
                "Margin balances are not identical to retail ownership or retail trading sentiment",
                "Credit-trading providers publish or revise data after close; report date is NOT publication timestamp"]}
    (data/"s2_credit_meta_29c.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("2.9C official credit balances",metadata["fresh_records"],"rows",per_market)
    return result,metadata
if __name__=="__main__":collect()
