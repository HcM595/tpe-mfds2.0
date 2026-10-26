#!/usr/bin/env python3
"""2.9F: immutable FIRST OBSERVATION ledger for official F2/F3 data versions.

Three separate clocks:
 (1) source_report_date: the reporting/as-of date printed by official APIs
 (2) observed_first_at_utc: when this website captured the raw source version
 (3) verified_publication_at_utc: separately evidenced first public release
      (missing today; NEVER infer from either (1) or (2)).

Not a retrospective database. Capturing a 2026-10-22 table on 2026-10-26
cannot make that data available for a 2026-10-22 backtest. We archive current
snapshots across daily runs and refuse to calculate prediction probabilities.
"""
import csv
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TZ=ZoneInfo("Asia/Taipei")
HISTORY_FIELDS=["stock_id","market","factor","source_report_date",
                "observed_first_at_utc","verified_publication_at_utc",
                "raw_source_sha256","source_url","observed_value_json",
                "historical_backtest_eligible"]
STOCK_FIELDS=["stock_id","stock_name","market","price_asof",
              "F2_source_report_date","F2_observed_first_at_utc","F2_publication_at_utc",
              "F2_source_status","F2_pit_status","F2_usable_for_backtest",
              "F3_source_report_date","F3_observed_first_at_utc","F3_publication_at_utc",
              "F3_source_status","F3_pit_status","F3_usable_for_backtest"]
FACTOR_META={
 "F2":("f2_valuation_29e.csv","asof",("pe_ratio","pb_ratio","dividend_yield_pct")),
 "F3":("f3_governance_29e.csv","source_asof",("chairman_is_general_manager",))
}
def read(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as fp:
        w=csv.DictWriter(fp,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        w.writeheader();w.writerows(rows)
def is_day(s):
    try:return isinstance(s,str) and dt.date.fromisoformat(s).isoformat()==s
    except (ValueError,TypeError):return False
def utc_instant(raw):
    if not isinstance(raw,str) or not raw.strip():return None
    try:
        z=dt.datetime.fromisoformat(raw.replace("Z","+00:00"))
        if z.tzinfo is None:return None
        return z.astimezone(dt.timezone.utc)
    except ValueError:return None
def sha_ok(raw):
    return isinstance(raw,str) and len(raw)==64 and all(c in "0123456789abcdef" for c in raw)
def audit_row(source,price_day,now):
    """Do not equate official period labels with actual release timestamps."""
    if not source:return "no_source"
    if source.get("source_status")!="ok":return "stale_or_unverified_snapshot"
    report=source.get("_report_day","")
    if not is_day(report):return "bad_source_report_date"
    if not is_day(price_day):return "missing_price_reference_date"
    if report>price_day:return "source_report_after_price"
    capture=utc_instant(source.get("first_seen_utc",""))
    if capture is None:return "missing_or_invalid_first_seen"
    if capture>now:return "capture_time_in_future"
    # Intraday cut-off is not independently established. Conservative
    # cutoff is start of price reference calendar day in Taiwan.
    price_start=dt.datetime.combine(dt.date.fromisoformat(price_day),dt.time.min,TZ)
    if capture>=price_start.astimezone(dt.timezone.utc):
        return "first_observed_after_price_cutoff"
    # Even if captured earlier, no independently verified official release
    # timestamp exists, so evidence cannot be approved for as-of backtests.
    return "official_publication_time_unverified"
def capture(root=ROOT,clock=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    if clock.tzinfo is None:raise ValueError("clock must be timezone-aware")
    clock=clock.astimezone(dt.timezone.utc)
    data=root/"site"/"data";data.mkdir(parents=True,exist_ok=True)
    snapshots=read(data/"official_snapshot.csv")
    latest={(r["stock_id"],r.get("market","")):r for r in snapshots
            if r.get("stock_id") and r.get("market") in ("上市","上櫃")}
    old_path=data/"pit_f2f3_source_versions_29f.csv"
    old=read(old_path)
    versions={}
    for row in old:
        key=(row.get("stock_id",""),row.get("market",""),
             row.get("factor",""),row.get("raw_source_sha256",""))
        if key in versions and versions[key]!=row:
            raise ValueError("existing PIT observation version collision; manual review required")
        if not sha_ok(key[-1]) or row.get("factor") not in FACTOR_META:
            raise ValueError("invalid previous PIT ledger row")
        versions[key]=row
    sources={}
    stats=Counter()
    for factor,(file,period_field,value_fields) in FACTOR_META.items():
        entries={}
        for row in read(data/file):
            sid=row.get("stock_id","")
            market=row.get("market","")
            if not sid or market not in ("上市","上櫃"):
                continue
            key=(sid,market)
            if key in entries:
                raise ValueError("duplicate stock-market in "+file)
            item=dict(row,_report_day=row.get(period_field,""))
            entries[key]=item
            valid=(item.get("source_status")=="ok" and
                   is_day(item["_report_day"]) and
                   sha_ok(item.get("source_sha256")) and
                   utc_instant(item.get("first_seen_utc")) is not None)
            if not valid:
                stats[factor+"_record_missing_provenance"]+=1
                continue
            # Do not accept a first observation in the future.
            if utc_instant(item["first_seen_utc"])>clock:
                stats[factor+"_record_future_first_seen"]+=1
                continue
            stock_key=(sid,market,factor,item["source_sha256"])
            fingerprint={field:item.get(field,"") for field in value_fields}
            value_json=json.dumps(fingerprint,ensure_ascii=False,sort_keys=True,separators=(",",":"))
            if stock_key not in versions:
                versions[stock_key]=dict(
                   stock_id=sid,market=market,factor=factor,
                   source_report_date=item["_report_day"],
                   observed_first_at_utc=item["first_seen_utc"],
                   verified_publication_at_utc="",
                   raw_source_sha256=item["source_sha256"],
                   source_url=item.get("source_url",""),
                   observed_value_json=value_json,
                   historical_backtest_eligible="false")
                stats["new_versions"]+=1
            else:
                # First-seen and raw observed content are append-only.
                prev=versions[stock_key]
                if prev.get("observed_value_json")!=value_json or prev.get("source_report_date")!=item["_report_day"]:
                    raise ValueError("same hash shows conflicting raw values/dates for "+sid+" "+factor)
        sources[factor]=entries
    # A source may be captured and later absent from the current snapshot;
    # version histories must not disappear.
    history=sorted(versions.values(),key=lambda r:(r["market"],r["stock_id"],r["factor"],r["observed_first_at_utc"],r["raw_source_sha256"]))
    write(old_path,HISTORY_FIELDS,history)
    output=[]
    for (sid,market),snap in sorted(latest.items(),key=lambda x:(x[0][1],x[0][0])):
        price=snap.get("asof","")
        record=dict(stock_id=sid,stock_name=snap.get("stock_name",""),market=market,price_asof=price)
        for factor in FACTOR_META:
            item=sources[factor].get((sid,market),{})
            record[factor+"_source_report_date"]=item.get("_report_day","")
            record[factor+"_observed_first_at_utc"]=item.get("first_seen_utc","")
            record[factor+"_publication_at_utc"]="" # No independently sourced publish timestamp
            record[factor+"_source_status"]=item.get("source_status","unavailable")
            status=audit_row(item,price,clock)
            record[factor+"_pit_status"]=status
            record[factor+"_usable_for_backtest"]="false"
            stats[factor+"_"+status]+=1
        output.append(record)
    write(data/"pit_f2f3_stock_29f.csv",STOCK_FIELDS,output)
    meta={
       "version":"2.9F",
       "generated_at_taipei":clock.astimezone(TZ).isoformat(timespec="seconds"),
       "whole_universe_stocks":len(output),"source_version_rows":len(history),
       "new_versions_this_run":stats["new_versions"],
       "factors":{},
       "three_clock_policy":{
           "source_report_date":"交易所/揭露表自帶的資料所屬日（非正式公開時分）",
           "observed_first_at_utc":"本站首次取得該原始內容SHA256版本的時間（不能倒推為公告日）",
           "verified_publication_at_utc":None
       },
       "cutoff_policy":"保守以股價基準日台灣00:00作首次封存比較；但任何官方公布時間未核對之資料皆不可作歷史回測",
       "strict_backtest_eligible":0,"model_scores_enabled":False,
       "probabilities_enabled":False,"raw_price_corporate_actions_adjusted":False,
       "notes":[
          "本次建立的逐股原始來源版本帳本只能記錄從現在起觀察到的版本；不能回填證交所過去的真正發布時分",
          "每日保存來源SHA256與首次取得時刻，同一來源版本再次取得不得覆蓋首次時刻或歷史值",
          "來源報表日<=股價日、本站首次封存<=股價日、官方獨立公布日已驗證是三項不同要求",
          "歷史可回測資格保持全數封閉，直至獨立官方發布時分、盤中截止時間與公司行動價格調整全部驗證"
       ]
    }
    for factor in FACTOR_META:
        meta["factors"][factor]={key.removeprefix(factor+"_"):value for key,value in stats.items() if key.startswith(factor+"_")}
    (data/"pit_f2f3_meta_29f.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return output,history,meta

if __name__=="__main__":
    rows,history,meta=capture()
    print("2.9F F2/F3 observed source versions",len(history),"stocks",len(rows),
          "new versions",meta["new_versions_this_run"],
          "strict PIT eligible",meta["strict_backtest_eligible"])
