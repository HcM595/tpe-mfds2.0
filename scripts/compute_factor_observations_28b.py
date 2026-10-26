#!/usr/bin/env python3
"""2.8B: reproducible *descriptive* S1 and S3 observations from archived data.

These are NOT model factor scores, forecasts, trade signals or adjusted returns.
A stock must have observations for EVERY archived market session in a window.
Do not replace missing data by zero; do not assume archived dates are an official calendar.
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
COLUMNS = [
    "stock_id", "stock_name", "market", "asof", "market_sessions_reference",
    "price_observations", "institutional_observations", "s1_5d_end", "s1_20d_end",
    "foreign_5d_net_shares", "trust_5d_net_shares",
    "foreign_5d_volume_ratio_pct", "trust_5d_volume_ratio_pct",
    "foreign_20d_net_shares", "trust_20d_net_shares",
    "foreign_20d_volume_ratio_pct", "trust_20d_volume_ratio_pct",
    "s3_ma20_raw", "s3_ma60_raw", "s3_momentum20_raw_pct",
    "s3_momentum60_raw_pct", "s3_vol20_raw_annualized_pct",
    "s1_status", "s3_status", "risk_notes",
]


def number(x):
    try:
        if x is None or str(x).strip() == "":
            return None
        n = float(str(x).replace(",", ""))
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def eligible_date(x):
    try:
        return dt.date.fromisoformat(x).isoformat() == x
    except (TypeError, ValueError):
        return False


def summarize_stock(code, name, market, asof, sessions, prices, flows):
    pmap = {r["date"]: r for r in prices if eligible_date(r.get("date")) and r["date"] <= asof}
    fmap = {r["date"]: r for r in flows if eligible_date(r.get("date")) and r["date"] <= asof}
    out = {k: "" for k in COLUMNS}
    out.update(stock_id=code, stock_name=name, market=market, asof=asof,
               market_sessions_reference="同市場價格封存紀錄推定日期，非官方獨立行事曆",
               price_observations=len(pmap), institutional_observations=len(fmap),
               s1_status="資料不足", s3_status="資料不足",
               risk_notes="未驗證除權息調整及逐筆資料公布時間；不供報酬回測或預測使用")
    market_days = [d for d in sessions if d <= asof]
    if not market_days or market_days[-1] != asof:
        out["s1_status"] = "市場日期參考未覆蓋快照日"
        out["s3_status"] = "市場日期參考未覆蓋快照日"
        return out

    # S1: 5/20 session matched flow, and daily trade volumes all present.
    for n in (5, 20):
        days = market_days[-n:]
        if len(days) < n:
            continue
        matches = [d for d in days if d in pmap and d in fmap and number(pmap[d].get("volume_shares")) is not None
                   and number(pmap[d].get("volume_shares")) > 0
                   and number(fmap[d].get("foreign_net_shares")) is not None
                   and number(fmap[d].get("trust_net_shares")) is not None]
        if len(matches) != n:
            continue
        volume = sum(number(pmap[d]["volume_shares"]) for d in days)
        if volume <= 0:
            continue
        for src, col in (("foreign_net_shares", "foreign"), ("trust_net_shares", "trust")):
            total = sum(number(fmap[d][src]) for d in days)
            out[f"{col}_{n}d_net_shares"] = str(int(round(total)))
            out[f"{col}_{n}d_volume_ratio_pct"] = round(total / volume * 100, 6)
        out[f"s1_{n}d_end"] = days[-1]
    if out["s1_5d_end"] and out["s1_20d_end"]:
        out["s1_status"] = "5及20交易日可核對（描述性）"
    elif out["s1_5d_end"]:
        out["s1_status"] = "僅5交易日可核對"
    else:
        out["s1_status"] = "有缺漏或日期不同步，不計算"

    # S3: raw closes need all market dates, including the lookback endpoint.
    def closes(n):
        days = market_days[-n:]
        if len(days) != n:
            return None
        vals = [number(pmap.get(d, {}).get("close")) for d in days]
        return vals if all(x is not None and x > 0 for x in vals) else None

    c20 = closes(20)
    c60 = closes(60)
    c21 = closes(21)
    c61 = closes(61)
    if c20:
        out["s3_ma20_raw"] = round(sum(c20) / 20, 4)
    if c60:
        out["s3_ma60_raw"] = round(sum(c60) / 60, 4)
    if c21:
        out["s3_momentum20_raw_pct"] = round((c21[-1] / c21[0] - 1) * 100, 4)
        lr = [math.log(c21[i] / c21[i - 1]) for i in range(1, len(c21))]
        mean = sum(lr) / len(lr)
        out["s3_vol20_raw_annualized_pct"] = round(
            math.sqrt(sum((v - mean) ** 2 for v in lr) / len(lr)) * math.sqrt(252) * 100, 4)
    if c61:
        out["s3_momentum60_raw_pct"] = round((c61[-1] / c61[0] - 1) * 100, 4)
    out["s3_status"] = ("原始收盤價完整61日（未調整）" if c61 else
                        "原始收盤價部分可計算（未調整）" if c20 else
                        "缺少連續20個已封存市場交易日價格")
    return out


def build(site=SITE, master=MASTER):
    snapshots = read_rows(site / "official_snapshot.csv")
    company = {r["stock_id"]: r for r in read_rows(master)}
    price_by = defaultdict(list)
    flow_by = defaultdict(list)
    count_day = defaultdict(Counter)
    for r in read_rows(site / "price_history.csv"):
        code, day = r.get("stock_id", ""), r.get("date", "")
        market = company.get(code, {}).get("market", "")
        if not eligible_date(day) or market not in ("上市", "上櫃"):
            continue
        price_by[code].append(r)
        if number(r.get("close")) is not None and number(r.get("close")) > 0:
            count_day[market][day] += 1
    for r in read_rows(site / "institutional_trend.csv"):
        flow_by[r.get("stock_id", "")].append(r)
    # All dates must have broad market participation; dates with only a few
    # archived stocks do not provide a trustworthy full-market session reference.
    market_dates = {m: sorted(d for d, count in counts.items() if count >= 50)
                    for m, counts in count_day.items()}
    results = []
    for snap in snapshots:
        sid = snap.get("stock_id", "")
        asof = snap.get("asof", "")
        market = snap.get("market", "")
        if sid not in company or not eligible_date(asof) or market not in market_dates:
            continue
        if market != company[sid].get("market"):
            continue
        results.append(summarize_stock(sid, snap.get("stock_name", sid), market, asof,
                                       market_dates[market], price_by[sid], flow_by[sid]))
    results.sort(key=lambda x: (x["market"], x["stock_id"]))
    site.mkdir(parents=True, exist_ok=True)
    with (site / "factor_observations_28b.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(results)
    counts = Counter()
    for r in results:
        counts["s1_full"] += bool(r["s1_20d_end"] and r["s1_5d_end"])
        counts["s1_partial"] += bool(r["s1_5d_end"] and not r["s1_20d_end"])
        counts["s3_momentum60"] += r["s3_momentum60_raw_pct"] != ""
        counts["s3_momentum20"] += r["s3_momentum20_raw_pct"] != ""
    meta = {
        "version": "2.8B", "generated_at_taipei": dt.datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
        "stocks": len(results), **counts, "status": "descriptive_only_not_model_eligible",
        "s1_unit": "各期間法人買賣超股數／同期間成交股數 ×100（百分比，非持股比例）",
        "s3_unit": "原始未調整收盤價；20/60日動能與20日年化對數波動率",
        "market_day_reference": "同市場封存價量涵蓋至少50檔時的實際觀察日期；不是獨立驗證的官方交易日曆",
        "corporate_actions_adjusted": False, "publication_times_verified": False,
        "factor_scores_enabled": False, "probability_enabled": False,
        "caveats": ["沒有OHLC不得計算ATR", "沒有除權息調整不得將原始動能解讀為實際總報酬",
                    "法人流量比率不代表外資持股比例", "各交易日來源可能缺漏；缺漏期間不補值不計算"],
    }
    (site / "factor_observations_meta_28b.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return results, meta


if __name__ == "__main__":
    rows, meta = build()
    print("2.8B descriptive S1/S3 observations", meta["stocks"], "s1_full", meta["s1_full"],
          "s3_60d", meta["s3_momentum60"])
