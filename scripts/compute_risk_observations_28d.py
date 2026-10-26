#!/usr/bin/env python3
"""2.8D: no-lookahead, close-only historical risk reference for swing research.

Do NOT call a closing-price range the traded high/low, ATR, or a price target.
No OHLC and no verified adjusted series; the output is descriptive only.
"""
import csv
import datetime as dt
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site" / "data"
MASTER = ROOT / "history_data" / "ordinary_stock_master.csv"
HEAD = (
    "stock_id","stock_name","market","price_asof","last_close","close_sessions",
    "prior20_close_high","prior20_close_low","prior60_close_high","prior60_close_low",
    "distance_prior20_high_pct","distance_prior20_low_pct",
    "distance_prior60_high_pct","distance_prior60_low_pct",
    "max_close_drawdown20_pct","max_close_drawdown60_pct",
    "realized_volatility20_annualized_pct","risk_status",
    "f1_revenue_available","f1_cashflow_profit_verified","f2_valuation_verified",
    "f3_governance_verified","finance_status","price_adjusted","atr_available",
)

def number(value):
    try:
        if value is None or str(value).strip() == "": return None
        n = float(str(value).replace(",",""))
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None

def date_valid(value):
    if not isinstance(value,str): return False
    try: return dt.date.fromisoformat(value).isoformat()==value
    except ValueError:return False

def read(path):
    with path.open(encoding="utf-8-sig",newline="") as fp:
        return list(csv.DictReader(fp))

def max_drawdown_from_closes(series):
    """Max peak-to-later-trough fall, <=0, using observed raw closing prices."""
    peak = series[0]
    worst = 0.0
    for p in series[1:]:
        peak = max(peak,p)
        worst = min(worst,(p / peak - 1) * 100)
    return round(worst,4)

def evaluate(code,name,market,asof,sessions,prices,revenue_ids):
    out = {k:"" for k in HEAD}
    out.update(stock_id=code,stock_name=name,market=market,price_asof=asof,
               risk_status="資料不足",f1_revenue_available="true" if code in revenue_ids else "false",
               f1_cashflow_profit_verified="false",f2_valuation_verified="false",
               f3_governance_verified="false",finance_status="未取得並核對現金流與淨利；不可形成F1／F2／F3分數",
               price_adjusted="false",atr_available="false")
    days = [d for d in sessions if d <= asof]
    if not days or days[-1] != asof:
        out["risk_status"]="市場日期未涵蓋本股價格快照日"
        return out
    pmap = {r.get("date"):number(r.get("close")) for r in prices if date_valid(r.get("date")) and r["date"] <= asof}
    last = pmap.get(asof)
    if last is None or last<=0:
        out["risk_status"]="最新價格缺失"
        return out
    out["last_close"]=round(last,4)
    out["close_sessions"]=len([d for d in days if (pmap.get(d) or 0)>0])
    # Requires today's close PLUS the exact preceding N common market sessions.
    available=[]
    for n in (20,60):
        needed=days[-(n+1):]
        if len(needed)<n+1: continue
        values=[pmap.get(d) for d in needed]
        if any(p is None or p<=0 for p in values): continue
        prior=values[:-1]
        high=max(prior);low=min(prior)
        out[f"prior{n}_close_high"]=round(high,4)
        out[f"prior{n}_close_low"]=round(low,4)
        out[f"distance_prior{n}_high_pct"]=round((last / high - 1)*100,4)
        out[f"distance_prior{n}_low_pct"]=round((last / low - 1)*100,4)
        out[f"max_close_drawdown{n}_pct"]=max_drawdown_from_closes(values)
        if n==20:
            changes=[math.log(values[i]/values[i-1]) for i in range(1,len(values))]
            avg=sum(changes)/len(changes)
            std=math.sqrt(sum((v-avg)**2 for v in changes)/len(changes))
            out["realized_volatility20_annualized_pct"]=round(std*math.sqrt(252)*100,4)
        available.append(n)
    out["risk_status"]=("20／60日完整（未還原收盤）" if len(available)==2
                         else "僅20日完整（未還原收盤）" if 20 in available
                         else "歷史價格或日期缺漏，不產生20／60日參考價")
    return out

def build(site=SITE, master=MASTER):
    stock_master = {r["stock_id"]:r for r in read(master)}
    snap=read(site/"official_snapshot.csv")
    history=defaultdict(list)
    calendar=defaultdict(Counter)
    for r in read(site/"price_history.csv"):
        code,day=r.get("stock_id",""),r.get("date","")
        market=stock_master.get(code,{}).get("market")
        p=number(r.get("close"))
        if not date_valid(day) or market not in ("上市","上櫃"):continue
        history[code].append(r)
        if p is not None and p>0:
            calendar[market][day]+=1
    market_sessions={m:sorted(d for d,c in counts.items() if c>=50) for m,counts in calendar.items()}
    rev_path=site/"revenue_snapshot_28c.csv"
    rev_ids={r.get("stock_id") for r in read(rev_path)} if rev_path.exists() else set()
    results=[]
    for stock in snap:
        sid,market,asof=stock.get("stock_id",""),stock.get("market",""),stock.get("asof","")
        if stock_master.get(sid,{}).get("market")!=market or not date_valid(asof):continue
        results.append(evaluate(sid,stock.get("stock_name",sid),market,asof,
                                market_sessions.get(market,[]),history.get(sid,[]),rev_ids))
    results.sort(key=lambda r:(r["market"],r["stock_id"]))
    site.mkdir(parents=True,exist_ok=True)
    with (site/"risk_observations_28d.csv").open("w",encoding="utf-8",newline="") as fp:
        wr=csv.DictWriter(fp,fieldnames=HEAD);wr.writeheader();wr.writerows(results)
    counts=Counter()
    for row in results:
        counts["ref20_available"]+=row["prior20_close_high"]!=""
        counts["ref60_available"]+=row["prior60_close_high"]!=""
        counts["revenue_observed"]+=row["f1_revenue_available"]=="true"
    meta={
        "version":"2.8D","generated_at_taipei":dt.datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
        "stocks":len(results),**counts,
        "period_definition":"價格快照日之前完整20／60個市場觀察日之最高及最低原始收盤價；不包含當天",
        "drawdown_definition":"在截至今日共21／61個連續市場觀察日內，原始收盤價的最大峰谷跌幅（非最大真實成交回撤）",
        "volatility_definition":"21個相鄰收盤價形成的20個對數報酬，年化sqrt(252)描述性歷史波動率",
        "market_dates":"同市場至少50檔有有效封存收盤的日期作研究基準，不代表獨立官方日曆已核對",
        "atr_supported":False,"ohlc_verified":False,"prices_corporate_action_adjusted":False,
        "f1_cashflow_profit_verified":False,"f2_valuation_verified":False,"f3_governance_verified":False,
        "factor_scores_enabled":False,"probability_enabled":False,"risk_target_prices_enabled":False,
        "warning":"本資料只描述過去收盤波動；價格未除權息還原，不能視為支撐壓力必然有效，更不能用來建立買賣價位、ATR、勝率或總報酬。"
    }
    (site/"risk_meta_28d.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return results,meta

if __name__=="__main__":
    rows,m=build()
    print("2.8D verified close-only observations",m["stocks"],m["ref20_available"],m["ref60_available"])
