#!/usr/bin/env python3
"""2.8C: equal-stock-weighted raw industry momentum compared to raw market median.

Uses ONLY previously archived S3 stock-level observations for that stock's same
price snapshot date. No corporate action correction or ex-post forecasting.
Industry classification uses archived official company master, scoped by market.
"""
import csv
import json
import statistics
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parents[1]
HEAD = ["stock_id","stock_name","market","industry_code","asof",
        "industry_name_from_revenue","industry_peers_20","industry_peers_60",
        "industry_median_momentum20_raw_pct","market_median_momentum20_raw_pct",
        "industry_relative20_raw_pp","industry_median_momentum60_raw_pct",
        "market_median_momentum60_raw_pct","industry_relative60_raw_pp","status",
        "price_adjusted","factor_I3_verified"]

def read(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def value(v):
    try:
        if v is None or str(v).strip()=="":return None
        import math
        n=float(str(v))
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None

def calculate(stock_rows, master, revenue=(), min_peers=5, min_market=50):
    company={r["stock_id"]:r for r in master if r.get("market") in ("上市","上櫃")}
    rev={r["stock_id"]:r for r in revenue}
    industry=defaultdict(list)
    markets=defaultdict(list)
    valid={}
    for r in stock_rows:
        code=r.get("stock_id","")
        co=company.get(code)
        if not co or co.get("market")!=r.get("market") or not co.get("sector") or not r.get("asof"):
            continue
        k=(r["market"],r["asof"])
        valid[code]=r
        markets[k].append(r)
        industry[(r["market"],r["asof"],co["sector"])].append(r)

    result=[]
    for code,r in sorted(valid.items(),key=lambda x:(x[1]["market"],x[0])):
        co=company[code]
        k=(r["market"],r["asof"])
        peers=industry[k+(co["sector"],)]
        universe=markets[k]
        record={x:"" for x in HEAD}
        record.update(stock_id=code,stock_name=r.get("stock_name",""),
                      market=r["market"],asof=r["asof"],industry_code=co["sector"],
                      industry_name_from_revenue=rev.get(code,{}).get("industry",""),
                      price_adjusted="false",factor_I3_verified="false")
        statuses=[]
        for n in (20,60):
            f=f"s3_momentum{n}_raw_pct"
            peer_vals=[value(x.get(f)) for x in peers]
            market_vals=[value(x.get(f)) for x in universe]
            peer_vals=[x for x in peer_vals if x is not None]
            market_vals=[x for x in market_vals if x is not None]
            record[f"industry_peers_{n}"]=len(peer_vals)
            if len(peer_vals)<min_peers or len(market_vals)<min_market:
                statuses.append(f"{n}日比較組資料不足")
                continue
            im=statistics.median(peer_vals)
            mm=statistics.median(market_vals)
            record[f"industry_median_momentum{n}_raw_pct"]=round(im,4)
            record[f"market_median_momentum{n}_raw_pct"]=round(mm,4)
            record[f"industry_relative{n}_raw_pp"]=round(im-mm,4)
            statuses.append(f"{n}日可描述")
        record["status"]="；".join(statuses)
        result.append(record)
    return result

def build(base=BASE):
    site=base/"site"/"data"
    master=read(base/"history_data"/"ordinary_stock_master.csv")
    obs=read(site/"factor_observations_28b.csv")
    revenue_file=site/"revenue_snapshot_28c.csv"
    rev=read(revenue_file) if revenue_file.exists() else []
    records=calculate(obs,master,rev)
    with (site/"industry_relative_28c.csv").open("w",newline="",encoding="utf-8") as fp:
        wr=csv.DictWriter(fp,fieldnames=HEAD)
        wr.writeheader()
        wr.writerows(records)
    counts=Counter()
    for r in records:
        for n in (20,60):
            counts[f"relative{n}_available"]+=r[f"industry_relative{n}_raw_pp"]!=""
    meta={"version":"2.8C","generated_at_taipei":datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
          "stocks":len(records),**counts,"status":"descriptive_only",
          "relative_strength_definition":"同市場相同行情日：同產業個股原始動能中位數 - 全市場個股原始動能中位數（百分點）",
          "minimum_industry_members":5,"minimum_market_members":50,
          "industry_source":"history_data/ordinary_stock_master.csv（分市場產業代碼；非整體跨市場對比）",
          "adjusted_prices":False,"official_independent_session_calendar_verified":False,
          "factor_I3_verified":False,"performance_metrics_enabled":False,
          "note":"使用未還原收盤價；遇除權息可能扭曲動能。非投資回報、非預測、非已校準12因子。"}
    (site/"industry_relative_meta_28c.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return records,meta

if __name__=="__main__":
    rows,meta=build()
    print("2.8C industry raw relative strength",meta["stocks"],meta["relative20_available"],meta["relative60_available"])
