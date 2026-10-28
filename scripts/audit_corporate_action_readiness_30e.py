#!/usr/bin/env python3
"""3.0E: official ex-right reference-price / raw-price observation audit.

We NEVER infer cash distribution, split ratios, adjusted OHLC, total returns,
buy/sell signals or historical publication eligibility from reference prices.
The observed preceding close may be compared to official prior-close for data
quality, but does not prove complete trading calendars or source coverage.
"""
import bisect
import csv
import datetime as dt
import json
import math
import re
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
COLS=["stock_id","stock_name","market","price_asof",
      "raw_close_days","history_events_observed","rolling_notices_observed",
      "history_events_in_latest20_observed_sessions",
      "history_events_in_latest60_observed_sessions",
      "latest_ex_date","last_official_prior_close","last_official_reference_price",
      "last_observed_preceding_raw_close",
      "prior_close_pairs_checked","prior_close_matches","prior_close_mismatches",
      "prior_close_missing","event_reference_semantics",
      "historical_source_failures","historical_completeness_verified",
      "cash_stock_distribution_terms_verified","adjusted_ohlc_verified",
      "total_return_calculation_allowed","research_status","research_reason"]
REGEX=re.compile(r"^[0-9]{4,6}$")
def csv_rows(p):
    if not p.is_file():raise FileNotFoundError(f"required source missing: {p}")
    with p.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def validated_date(s):
    if not isinstance(s,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",s):return False
    try:return dt.date.fromisoformat(s).isoformat()==s
    except ValueError:return False
def price_num(s):
    try:
        if s is None or str(s).strip()=="":return None
        n=float(str(s).replace(",",""))
        return n if math.isfinite(n) and n>0 else None
    except (ValueError,TypeError):return None
def norm_market(raw):
    return {"TWSE":"上市","TPEx":"上櫃","上市":"上市","上櫃":"上櫃"}.get(raw,"")
def audit(root=ROOT):
    root=Path(root);data=root/"site"/"data"
    factor=csv_rows(data/"factor_evidence_29a.csv")
    prices=csv_rows(data/"price_history.csv")
    history=csv_rows(data/"corporate_action_history_events.csv")
    rolling=csv_rows(data/"corporate_actions_observed.csv")
    sources=csv_rows(data/"corporate_action_history_sources.csv")
    hmeta=json.loads((data/"corporate_action_history_meta.json").read_text(encoding="utf-8"))
    rmeta=json.loads((data/"corporate_actions_meta.json").read_text(encoding="utf-8"))
    if not factor or hmeta.get("historical_corporate_actions_complete") is not False or rmeta.get("historical_corporate_actions_complete") is not False:
        raise ValueError("Cannot authorize adjustments: incomplete corporate-action source contract")
    if hmeta.get("cash_or_stock_distribution_terms_verified") is not False or hmeta.get("adjusted_ohlc_verified") is not False or rmeta.get("adjusted_ohlc_verified") is not False:
        raise ValueError("Unverified distribution and adjusted-price contract changed; audit requires review")
    stocks={}
    for r in factor:
        sid=r.get("stock_id","")
        if sid in stocks or not REGEX.fullmatch(sid) or norm_market(r.get("market"))!=r.get("market") or not validated_date(r.get("price_asof")):
            raise ValueError("Bad/duplicate factor master identity or date "+sid)
        stocks[sid]=r
    raw=defaultdict(dict)
    for r in prices:
        sid,d=r.get("stock_id",""),r.get("date","")
        if sid not in stocks or not validated_date(d):continue
        value=price_num(r.get("close"))
        if value is None:continue
        old=raw[sid].get(d)
        if old is not None and abs(old-value)>0.0001:
            raise ValueError("Conflicting raw close on same stock/day "+sid+" "+d)
        raw[sid][d]=value
    events=defaultdict(list)
    seen=set()
    for r in history:
        sid,market=r.get("stock_id",""),norm_market(r.get("market"))
        day=r.get("ex_date","")
        if sid not in stocks or not validated_date(day) or stocks[sid]["market"]!=market:continue
        if not re.fullmatch(r"[a-f0-9]{64}",r.get("source_sha256","")):
            raise ValueError("Official history event missing verifiable source fingerprint: "+sid)
        if r.get("field_semantics")!="reference_price_components_not_share_distribution":
            raise ValueError("Unknown ex-right value meaning: "+sid)
        identity=(sid,market,day,r.get("event_type",""))
        if identity in seen:raise ValueError("Conflicting/duplicated history event identity "+str(identity))
        seen.add(identity)
        events[sid].append(r)
    notices=defaultdict(list)
    rseen=set()
    for r in rolling:
        sid,market=r.get("stock_id",""),norm_market(r.get("market"))
        day=r.get("ex_date","")
        if sid not in stocks or not validated_date(day) or stocks[sid]["market"]!=market:continue
        k=(sid,market,day,r.get("event_type",""))
        if k in rseen:raise ValueError("Duplicate rolling notice identity "+str(k))
        rseen.add(k);notices[sid].append(r)
    bad_runs=sum(r.get("result")!="events_archived" for r in sources)
    output=[];counts=Counter()
    for sid,b in sorted(stocks.items(),key=lambda kv:(kv[1]["market"],kv[0])):
        asof=b["price_asof"]
        observations=sorted((d,c) for d,c in raw[sid].items() if d<=asof)
        dates=[d for d,_ in observations]
        visible=sorted((e for e in events[sid] if e["ex_date"]<=asof),
                       key=lambda e:(e["ex_date"],e.get("event_type","")))
        count20=sum(bool(len(dates)>=21 and e["ex_date"]>=dates[-21]) for e in visible)
        count60=sum(bool(len(dates)>=61 and e["ex_date"]>=dates[-61]) for e in visible)
        checked=match=mismatch=missing=0
        last=visible[-1] if visible else {}
        last_prior=""
        for e in visible:
            # Date of latest observed close before the ex date; no inference of
            # an independently verified exchange calendar from missing bars.
            idx=bisect.bisect_left(dates,e["ex_date"])-1
            prior=observations[idx][1] if idx>=0 else None
            official=price_num(e.get("pre_close"))
            if prior is None or official is None:
                missing+=1
            else:
                checked+=1
                if abs(prior-official)<=0.051:match+=1
                else:mismatch+=1
            if e is last:last_prior=str(prior) if prior is not None else ""
        status=("原始前收不一致_需核對" if mismatch else
                "有官方歷史事件_尚缺完整還原" if visible else
                "未觀察到歷史事件_不得推定無除權息")
        reason=("官方參考價及前收僅是觀察欄位；不代表已核實股利、配股、除權息全期間或全部歷史市場交易日。"
                "來源曾失敗或資料有缺漏，且未產生經核對的調整OHLC。")
        output.append(dict(stock_id=sid,stock_name=b.get("stock_name",""),market=b["market"],price_asof=asof,
            raw_close_days=str(len(observations)),
            history_events_observed=str(len(visible)),
            rolling_notices_observed=str(len(notices[sid])),
            history_events_in_latest20_observed_sessions=str(count20),
            history_events_in_latest60_observed_sessions=str(count60),
            latest_ex_date=last.get("ex_date",""),
            last_official_prior_close=last.get("pre_close",""),
            last_official_reference_price=last.get("reference_price",""),
            last_observed_preceding_raw_close=last_prior,
            prior_close_pairs_checked=str(checked),
            prior_close_matches=str(match),
            prior_close_mismatches=str(mismatch),
            prior_close_missing=str(missing),
            event_reference_semantics="official_reference_price_not_cash_dividend_or_adjustment_factor",
            historical_source_failures=str(bad_runs),
            historical_completeness_verified="false",
            cash_stock_distribution_terms_verified="false",
            adjusted_ohlc_verified="false",
            total_return_calculation_allowed="false",
            research_status=status,research_reason=reason))
        counts["with_historical_event"]+=bool(visible)
        counts["mismatched_prior_close_stocks"]+=bool(mismatch)
        counts["events_latest60"]+=count60
        counts["prior_close_checked"]+=checked
        counts["prior_close_mismatches"]+=mismatch
    out=data/"corporate_action_readiness_30e.csv"
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=COLS,lineterminator="\n")
        w.writeheader();w.writerows(output)
    meta={
      "version":"3.0E","stocks":len(output),"source_price_asof":max(x["price_asof"] for x in output),
      "stocks_with_observed_official_historical_events":counts["with_historical_event"],
      "official_events_in_latest60_observed_sessions":counts["events_latest60"],
      "prior_raw_close_pairs_checked":counts["prior_close_checked"],
      "prior_raw_close_mismatches":counts["prior_close_mismatches"],
      "stocks_with_prior_close_mismatch":counts["mismatched_prior_close_stocks"],
      "failed_or_unverified_history_source_attempts":bad_runs,
      "historical_completeness_verified":False,
      "adjusted_ohlc_verified":False,
      "cash_stock_distribution_terms_verified":False,
      "total_return_calculation_allowed":False,
      "formal_model_scores_enabled":False,
      "probability_enabled":False,
      "warning":"已觀察除權息事件及前收比對屬資料品質稽核，不構成股利或配股完整認證；沒有事件不代表確定沒有。參考價不可取代現金分配或總報酬還原；價格、回測與勝率繼續停用。"
    }
    (data/"corporate_action_readiness_meta_30e.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return output,meta
if __name__=="__main__":
    a,m=audit()
    print("3.0E audit",len(a),"stocks; observed action",m["stocks_with_observed_official_historical_events"],
          "prior raw-close checks",m["prior_raw_close_pairs_checked"],"adjusted OHLC false")
