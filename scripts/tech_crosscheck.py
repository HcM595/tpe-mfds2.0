#!/usr/bin/env python3
"""TPE-MFDS 2.3.3: auditable descriptive technical/chip cross-check.

Inputs: site/data/chip_rank.csv, site/data/price_history.csv (from existing pipeline).
Outputs: site/data/tech_crosscheck.csv, site/data/tech_crosscheck_meta.json.
This DOES NOT change 2.3 chip ranking, return predictions, or trade signals.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "site" / "data"
COLUMNS = [
    "stock_id", "stock_name", "rank_status", "chip_strength_rank",
    "chip_strength_score", "price_asof", "flow_asof", "holder_asof",
    "history_days", "latest_history_date", "data_status",
    "close", "ma20", "ma20_previous", "ma20_rising", "close_above_ma20",
    "ma60", "rsi14", "rsi_note", "macd_diff", "macd_signal",
    "macd_hist", "macd_hist_previous", "macd_hist_improving",
    "technical_checks", "technical_confirmed_count", "technical_status",
    "mid400_999_4w_pp", "large1000_4w_pp", "holder_structure",
    "holder_anomaly", "note"
]

def read_csv(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"缺少輸入檔案: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def num(value):
    try:
        v = float(str(value).strip().replace(",", ""))
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None

def valid_iso(value):
    try:
        return dt.date.fromisoformat(str(value).strip()).isoformat()
    except (TypeError, ValueError):
        return None

def ema_full(values, length):
    """SMA-seeded EMA, identical to the existing website method."""
    if len(values) < length: return [None] * len(values)
    out = [None] * (length - 1)
    e = sum(values[:length]) / length
    out.append(e)
    alpha = 2 / (length + 1)
    for price in values[length:]:
        e = price * alpha + e * (1 - alpha)
        out.append(e)
    return out

def macd_history(prices):
    if len(prices) < 35: return []
    short, long = ema_full(prices, 12), ema_full(prices, 26)
    diff = [a-b if a is not None and b is not None else None for a,b in zip(short,long)]
    valid = [v for v in diff if v is not None]
    signals = ema_full(valid, 9)
    # Diff starts at price index 25; signal first exists at index 33.
    hist = [None] * len(prices)
    for i in range(25, len(prices)):
        sig_idx = i - 25
        if signals[sig_idx] is not None:
            hist[i] = (diff[i], signals[sig_idx], diff[i] - signals[sig_idx])
    return hist

def rsi_wilder(prices, length=14):
    if len(prices) < length + 1: return None
    diffs = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gain = sum(max(0,d) for d in diffs[:length]) / length
    loss = sum(max(0,-d) for d in diffs[:length]) / length
    for d in diffs[length:]:
        gain = (gain*(length-1) + max(d,0)) / length
        loss = (loss*(length-1) + max(-d,0)) / length
    if loss == 0: return 50.0 if gain == 0 else 100.0
    return 100.0 - 100.0 / (1 + gain/loss)

def history_index(rows):
    grouped = defaultdict(dict)
    for r in rows:
        code = str(r.get("stock_id","")).strip()
        day = valid_iso(r.get("date"))
        close = num(r.get("close"))
        if day and code.isdigit() and len(code)==4 and close is not None and close>0:
            grouped[code][day] = close
    return {k: sorted(v.items()) for k,v in grouped.items()}

def fnum(n, precision=5):
    return "" if n is None else round(n,precision)

def structure(mid, giant):
    if mid is None or giant is None: return "資料不足"
    if mid > 0 and giant > 0: return "雙級距增加"
    if (mid > 0 and giant < 0) or (mid < 0 and giant > 0): return "持股結構分歧"
    if (mid > 0 and giant == 0) or (mid == 0 and giant > 0): return "單級距增加，另一級距持平"
    return "雙級距未同增"

def calc_row(r, series):
    out = {k:"" for k in COLUMNS}
    for k in ("stock_id","stock_name","rank_status","chip_strength_rank",
              "chip_strength_score","price_asof","flow_asof","holder_asof"):
        out[k] = r.get(k,"")
    mid,giant = num(r.get("mid400_999_4w_pp")),num(r.get("large1000_4w_pp"))
    out["mid400_999_4w_pp"] = fnum(mid,4)
    out["large1000_4w_pp"] = fnum(giant,4)
    out["holder_structure"] = structure(mid, giant)
    l400 = num(r.get("large400_4w_pp"))
    out["holder_anomaly"] = ("四週變動幅度較大，需核實" if
                              any(abs(x)>=8 for x in (l400,giant,mid) if x is not None)
                              else "")
    code = str(r.get("stock_id","")).strip()
    pts = series.get(code, [])
    expected_date = valid_iso(r.get("price_asof"))
    if not expected_date:
        out["data_status"] = "無有效股價日期"
        out["note"] = "無法確認歷史價格日期"
        return out
    pts = [(d,c) for d,c in pts if d<=expected_date]
    out["history_days"] = len(pts)
    out["latest_history_date"] = pts[-1][0] if pts else ""
    if not pts or pts[-1][0] != expected_date:
        out["data_status"] = "股價日期不一致"
        out["note"] = "歷史資料最新日期不等於籌碼排名股價日期，暫不給技術確認"
        return out
    if expected_date != valid_iso(r.get("flow_asof")):
        out["data_status"] = "法人與股價日期不一致"
        out["note"] = "價格與法人日期不同，技術結果暫不作交叉確認"
        return out
    prices = [c for _,c in pts]
    out["close"] = fnum(prices[-1],4)
    if len(prices)<36:
        out["data_status"]="技術歷史不足"
        out["note"]="至少36個有效收盤日才能比較MACD柱變化"
        # Keep unavailable technical checks blank, never represent missing as negative.
        return out
    ma20 = sum(prices[-20:])/20
    ma20_prev = sum(prices[-21:-1])/20
    ma60 = sum(prices[-60:])/60 if len(prices)>=60 else None
    rsi = rsi_wilder(prices)
    macds = macd_history(prices)
    cur,prev = macds[-1],macds[-2]
    if cur is None or prev is None or rsi is None:
        out["data_status"]="技術歷史不足"
        out["note"]="無法比較MACD柱或計算RSI"
        return out
    close_high = prices[-1]>ma20
    ma_rising = ma20>ma20_prev
    macd_improve=cur[2]>prev[2]
    checks = sum((close_high,ma_rising,macd_improve))
    out.update(
        data_status="可驗證" if r.get("rank_status")=="可排名" else "技術可計算；籌碼未排名",
        ma20=fnum(ma20,4), ma20_previous=fnum(ma20_prev,4),
        ma20_rising="是" if ma_rising else "否",
        close_above_ma20="是" if close_high else "否",
        ma60=fnum(ma60,4), rsi14=fnum(rsi,2),
        rsi_note=("RSI偏高（≥70）" if rsi>=70 else "RSI偏低（≤30）" if rsi<=30 else "一般區間"),
        macd_diff=fnum(cur[0]),macd_signal=fnum(cur[1]),
        macd_hist=fnum(cur[2]),macd_hist_previous=fnum(prev[2]),
        macd_hist_improving="是" if macd_improve else "否",
        technical_checks="收盤高於MA20／MA20上升／MACD柱改善",
        technical_confirmed_count=checks,
        technical_status=("三項確認" if checks==3 else "部分確認" if checks in (1,2) else "尚未確認"),
        note="技術狀態不影響原籌碼分數；RSI僅供風險觀察；未還原除權息",
    )
    return out

def run(data_dir=DEFAULT_DATA):
    data_dir=Path(data_dir)
    ranks=read_csv(data_dir/"chip_rank.csv")
    history=read_csv(data_dir/"price_history.csv")
    if not ranks or not history: raise RuntimeError("排名或歷史行情檔案為空")
    series=history_index(history)
    result=[calc_row(r,series) for r in ranks]
    out_file=data_dir/"tech_crosscheck.csv"
    with out_file.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=COLUMNS)
        writer.writeheader();writer.writerows(result)
    eligible=[r for r in result if r["rank_status"]=="可排名"]
    status=Counter(r["data_status"] for r in eligible)
    tech=Counter(r["technical_status"] for r in eligible)
    holders=Counter(r["holder_structure"] for r in eligible)
    meta={
        "version":"2.3.3",
        "generated_at_taipei":dt.datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
        "status":"ok" if eligible and status.get("可驗證",0)==len(eligible) else "partial",
        "rank_candidates":len(ranks),"eligible_ranked":len(eligible),
        "eligible_verified":status.get("可驗證",0),
        "technical_status_counts":dict(tech),
        "holder_structure_counts":dict(holders),
        "eligible_data_status_counts":dict(status),
        "anomaly_count":sum(bool(r["holder_anomaly"]) for r in eligible),
        "checks":["close > MA20","MA20 > previous MA20","MACD_hist > previous MACD_hist"],
        "rsi_period":14,"macd_periods":[12,26,9],
        "source_files":["chip_rank.csv","price_history.csv"],
        "notes":["籌碼分數及名次完全沿用2.3，不重新評分，也不產生預測勝率。",
                 "技術確認3項計數，與籌碼分數分開；RSI為觀察值。",
                 "大戶結構為400至999張與1000張以上兩個不重疊級距的變化。",
                 "缺資料及日期不符時不推測技術方向；股價未還原除權息。",
                 "集保歷史部分使用非官方資料鏡像，異常變動需要核實。"]
    }
    (data_dir/"tech_crosscheck_meta.json").write_text(
        json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"2.3.3 tech crosscheck: {meta['eligible_verified']}/{len(eligible)} valid; " +
          f"3 checks={tech.get('三項確認',0)}; divergence={holders.get('持股結構分歧',0)}")
    return meta, result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--data-dir",type=Path,default=DEFAULT_DATA)
    args=p.parse_args()
    run(args.data_dir)
