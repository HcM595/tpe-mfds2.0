#!/usr/bin/env python3
"""2.9A: original 4-layer / 12-factor evidence matrix for Engines A and B.

States: no_data < partial < descriptive. NONE denotes an eligible trained factor.
There is no factor score, probability, expected return or performance claim.
Source observation timestamps do not prove point-in-time publication. A recent
archival snapshot can be newer than the stock's referenced price date.
"""
import csv
import bisect
import calendar
import datetime as dt
import json
import math
from collections import Counter,defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/"site"/"data"
MASTER=ROOT/"history_data"/"ordinary_stock_master.csv"
FACTOR_IDS=("M1","M2","M3","I1","I2","I3","F1","F2","F3","S1","S2","S3")
STATES=("no_data","partial","descriptive")
MIN_PRICE_DAYS=120
MIN_TURNOVER=30_000_000
TURNOVER_WINDOW=20
HEAD=["stock_id","stock_name","market","price_asof","master_market_match",
      "price_sessions","latest_history_date","avg20_trade_value_twd",
      "basic_data_status","basic_data_eligible","observed_factor_count",
      "partial_factor_count","descriptive_factor_count",
      "verified_factor_count","verified_coverage_pct",
      "source_postdates_price","factor_coverage_initial_60_pass",
      "factor_coverage_target_75_pass","model_eligible","prediction_enabled"]+[
      f"{factor}_{field}" for factor in FACTOR_IDS for field in ("state","asof")
]
def load(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as fp:return list(csv.DictReader(fp))
def indexed(path):
    return {r["stock_id"]:r for r in load(path) if r.get("stock_id")}
def number(v):
    try:
        if v is None or str(v).strip()=="":return None
        x=float(str(v).replace(",",""))
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None
def iso(s):
    if not isinstance(s,str):return False
    try:return dt.date.fromisoformat(s).isoformat()==s
    except (TypeError,ValueError):return False

def eligibility(prices,asof,market_match,min_days=MIN_PRICE_DAYS):
    # Replicates the site's basic 120/20d rule; this is NOT a proof that
    # the history includes every official trading day or is adjusted OHLC.
    distinct={}
    for p in prices:
        if iso(p.get("date")) and number(p.get("close")) is not None and number(p["close"])>0:
            distinct[p["date"]]=p
    days=sorted(distinct)
    count=len(days)
    latest=days[-1] if days else ""
    recent=[distinct[d] for d in days[-TURNOVER_WINDOW:]]
    vals=[number(p.get("trade_value_twd")) for p in recent]
    avg=(sum(vals)/TURNOVER_WINDOW if len(vals)==TURNOVER_WINDOW and
         all(x is not None and x>=0 for x in vals) else None)
    status=("普通股候選名錄或市場身分未確認" if not market_match else
            "歷史資料不足" if count<min_days else
            "近20日成交額資料不足" if avg is None else
            "歷史資料尚未對齊最新收盤日" if latest!=asof else
            "流動性未達門檻" if avg<MIN_TURNOVER else
            "初步通過歷史與流動性（非12因子資格）")
    return dict(price_sessions=count,latest_history_date=latest,
                avg20_trade_value_twd=round(avg,2) if avg is not None else "",
                basic_data_status=status,
                basic_data_eligible="true" if status.startswith("初步通過") else "false")

def build_row(snap,master,prices,obs,industry,revenue,income,cashflow,ytd,
              holder,dayflow,macro=None,fx_observation=None,s2_credit=None,sector_breadth=None,f2_valuation=None,f3_governance=None):
    sid=snap["stock_id"]; asof=snap.get("asof","")
    market=snap.get("market","")
    id_ok=bool(master and master.get("market")==market and market in ("上市","上櫃"))
    base=eligibility(prices,asof,id_ok)
    out={k:"" for k in HEAD}
    out.update(stock_id=sid,stock_name=snap.get("stock_name",""),market=market,
               price_asof=asof,master_market_match=str(id_ok).lower(),
               **base,observed_factor_count=0,partial_factor_count=0,
               descriptive_factor_count=0,verified_factor_count=0,
               verified_coverage_pct=0,source_postdates_price="false",
               factor_coverage_initial_60_pass="false",
               factor_coverage_target_75_pass="false",model_eligible="false",
               prediction_enabled="false")
    def set_factor(fid,condition,full=False,date=""):
        # No factor can be 'verified' until publication-time, transformations
        # and walk-forward requirements have independently passed.
        state="descriptive" if condition and full else "partial" if condition else "no_data"
        out[f"{fid}_state"]=state
        out[f"{fid}_asof"]=date if condition and iso(date) else ""
    macro=macro or {}
    current_month=asof[:4]+asof[5:7] if iso(asof) else ""
    def reference_month(period):
        if not isinstance(period,str) or len(period)!=6 or not period.isdigit() or period>current_month:
            return ""
        y,month=int(period[:4]),int(period[4:])
        try:return dt.date(y,month,calendar.monthrange(y,month)[1]).isoformat()
        except ValueError:return ""
    signal=macro.get("M1") or {}
    export=macro.get("M2") or {}
    fx=fx_observation or {}
    m1_end=reference_month(signal.get("observation_period",""))
    m1_full=bool(m1_end) and number(signal.get("composite_score")) is not None and signal.get("light") in ("藍","黃藍","綠","黃紅","紅")
    set_factor("M1",m1_full,full=m1_full,date=m1_end)  # observation ONLY; release timestamp not verified
    m2_end=reference_month(export.get("export_period",""))
    m2_evidence=bool(m2_end) and (number(export.get("export_yoy_pct")) is not None or number(export.get("order_direction_index")) is not None)
    set_factor("M2",m2_evidence,date=m2_end)  # order-count direction is NOT orders amount growth
    fx_available=bool(fx.get("date")) and fx["date"]<=asof and number(fx.get("usd_twd_close")) is not None
    local_flow=number(obs.get("foreign_20d_volume_ratio_pct")) is not None and bool(obs.get("stock_id"))
    set_factor("M3",fx_available or local_flow,
               date=fx.get("date","") if fx_available else obs.get("s1_20d_end",""))
    # USD/TWD alone + stock flow are not an independently verified market-wide foreign flow factor.
    # The original I1 is SEMICONDUCTOR CYCLE, not any listed firm's revenue.
    # Even peer YoY diffusion is only partial until inventory and multi-period
    # business-cycle chronology are sourced and point-in-time dates checked.
    breadth=sector_breadth or {}
    semi=master.get("sector")=="24"
    breadth_ok=(semi and breadth.get("stock_id")==sid and
                breadth.get("market")==market and breadth.get("sector")=="24" and
                breadth.get("period")==revenue.get("revenue_period") and
                number(breadth.get("growth_diffusion_pct")) is not None and
                iso(breadth.get("table_date","")) and breadth["table_date"]<=asof)
    set_factor("I1",breadth_ok,date=breadth.get("table_date",""))
    # An authenticated Ministry announcement alone does NOT identify this
    # stock's eligibility, economic benefit, or a causal impact.
    set_factor("I2",False)
    relative20=number(industry.get("industry_relative20_raw_pp"))
    relative60=number(industry.get("industry_relative60_raw_pp"))
    industry_date=industry.get("asof","")
    sector_data=relative20 is not None and relative60 is not None and industry_date==asof
    set_factor("I3",sector_data,full=sector_data,date=industry_date)
    cf_observed=cashflow.get("source_status") in ("ok","not_checked_this_run","stale_backup")
    ytd_observed=bool(ytd.get("income_ytd_net_profit_raw"))
    income_proof=ytd.get("cashflow_period_matched")=="true" and ytd.get("report_period")==cashflow.get("report_period")
    revenue_data=bool(revenue.get("revenue_period"))
    # Descriptive F1 requires all three, but NEVER verifies consolidation/publication.
    f1_evidence=revenue_data or cf_observed or ytd_observed
    set_factor("F1",f1_evidence,full=(revenue_data and cf_observed and income_proof),
               date=revenue.get("table_date",""))
    valuation=f2_valuation or {}
    governance=f3_governance or {}
    valuation_date=valuation.get("asof","")
    f2_valid=(valuation.get("stock_id")==sid and valuation.get("market")==market and
              iso(valuation_date) and valuation_date<=asof and
              valuation.get("peer_f2_ready")=="true" and
              number(valuation.get("pe_ratio")) is not None and
              number(valuation.get("pb_ratio")) is not None and
              number(valuation.get("pe_peer_median")) is not None and
              number(valuation.get("pb_peer_median")) is not None)
    # F2 contains expectations/surprise; a peer quote ratio alone is partial.
    set_factor("F2",f2_valid,date=valuation_date if f2_valid else "")
    gov_date=governance.get("source_asof","")
    f3_valid=(governance.get("stock_id")==sid and governance.get("market")==market and
              iso(gov_date) and gov_date<=asof and
              governance.get("chairman_is_general_manager") in ("true","false"))
    # Chair/CEO overlap is descriptive, never a governance quality rating.
    set_factor("F3",f3_valid,date=gov_date if f3_valid else "")
    s1=bool(obs.get("stock_id")) and obs.get("asof")==asof and bool(obs.get("s1_5d_end")) and all(number(obs.get(k)) is not None for k in ("foreign_5d_volume_ratio_pct","trust_5d_volume_ratio_pct"))
    s1_full=s1 and bool(obs.get("s1_20d_end")) and all(number(obs.get(k)) is not None for k in ("foreign_20d_volume_ratio_pct","trust_20d_volume_ratio_pct"))
    set_factor("S1",s1,full=s1_full,date=obs.get("s1_20d_end") or obs.get("s1_5d_end",""))
    # Margin balances are credit leverage observations, not measured retail sentiment.
    # Large-holder concentrations are NOT substitutes for financing or day-trading.
    credit=s2_credit or {}
    credit_date=credit.get("report_date","")
    credit_valid=bool(iso(credit_date) and credit_date<=asof and
                  credit.get("stock_id")==sid and
                  number(credit.get("margin_balance_units")) is not None and
                  number(credit.get("short_balance_units")) is not None)
    set_factor("S2",credit_valid,date=credit_date if credit_valid else "")
    s3=bool(obs.get("stock_id")) and obs.get("asof")==asof and number(obs.get("s3_momentum20_raw_pct")) is not None
    set_factor("S3",s3,full=s3 and number(obs.get("s3_momentum60_raw_pct")) is not None,
               date=obs.get("asof",""))
    states=[out[f"{factor}_state"] for factor in FACTOR_IDS]
    out["partial_factor_count"]=states.count("partial")
    out["descriptive_factor_count"]=states.count("descriptive")
    out["observed_factor_count"]=out["partial_factor_count"]+out["descriptive_factor_count"]
    # Null publication date in legacy factor manifest, or first snapshot after
    # reference date, must NEVER be counted as time-valid for scoring.
    timestamps=[r.get("first_seen_utc","") for r in (revenue,income,cashflow,ytd)]
    timestamps += [(macro.get("sources",{}).get(key) or {}).get("first_seen_utc","") for key in ("ndc","cbc")]
    timestamps.append(credit.get("first_seen_utc",""))
    timestamps.extend([valuation.get("first_seen_utc",""),governance.get("first_seen_utc","")])
    later=False
    for stamp in timestamps:
        if stamp and iso(asof):
            try:
                if dt.datetime.fromisoformat(stamp.replace("Z","+00:00")).date()>dt.date.fromisoformat(asof):
                    later=True
            except ValueError:pass
    out["source_postdates_price"]=str(later).lower()
    return out

def build(root=ROOT):
    site=root/"site"/"data"
    snapshot=load(site/"official_snapshot.csv")
    masters=indexed(root/"history_data"/"ordinary_stock_master.csv")
    obs=indexed(site/"factor_observations_28b.csv")
    ind=indexed(site/"industry_relative_28c.csv")
    rev=indexed(site/"revenue_snapshot_28c.csv")
    inc=indexed(site/"income_snapshot_28f.csv")
    cf=indexed(site/"cashflow_focus_28g.csv")
    ytd=indexed(site/"mops_income_ytd_28i.csv")
    holders=indexed(site/"chip_signals.csv")
    flows=indexed(site/"chip_rank.csv")
    credits=indexed(site/"s2_credit_snapshot_29c.csv")
    breadth=indexed(site/"industry_breadth_29d.csv")
    f2=indexed(site/"f2_valuation_29e.csv")
    f3=indexed(site/"f3_governance_29e.csv")
    macro_path=site/"macro_snapshot_29b.json"
    macro=json.loads(macro_path.read_text(encoding="utf-8")) if macro_path.is_file() else {}
    fxrows=[r for r in load(site/"macro_fx_history_29b.csv")
            if iso(r.get("date")) and number(r.get("usd_twd_close")) is not None]
    fxrows.sort(key=lambda r:r["date"])
    fxdates=[r["date"] for r in fxrows]
    prices=defaultdict(list)
    for p in load(site/"price_history.csv"):
        if p.get("stock_id"):prices[p["stock_id"]].append(p)
    output=[]
    for s in snapshot:
        sid=s.get("stock_id","")
        if not sid or not iso(s.get("asof")):continue
        if not s.get("market") in ("上市","上櫃"):continue
        at=bisect.bisect_right(fxdates,s["asof"])-1
        prior_fx=fxrows[at] if at>=0 else {}
        output.append(build_row(s,masters.get(sid,{}),prices.get(sid,[]),
                     obs.get(sid,{}),ind.get(sid,{}),rev.get(sid,{}),
                     inc.get(sid,{}),cf.get(sid,{}),ytd.get(sid,{}),
                     holders.get(sid,{}),flows.get(sid,{}),macro,prior_fx,credits.get(sid,{}),breadth.get(sid,{}),f2.get(sid,{}),f3.get(sid,{})))
    output.sort(key=lambda x:(x["market"],x["stock_id"]))
    site.mkdir(parents=True,exist_ok=True)
    with (site/"factor_evidence_29a.csv").open("w",encoding="utf-8",newline="") as fp:
        wr=csv.DictWriter(fp,fieldnames=HEAD,lineterminator="\n");wr.writeheader();wr.writerows(output)
    cnt=Counter()
    factor_counts={}
    for fid in FACTOR_IDS:
        states=Counter(x[f"{fid}_state"] for x in output)
        factor_counts[fid]=dict(no_data=states["no_data"],partial=states["partial"],
                                descriptive=states["descriptive"],verified=0)
    cnt["base_qualified"]=sum(x["basic_data_eligible"]=="true" for x in output)
    cnt["source_postdates_price"]=sum(x["source_postdates_price"]=="true" for x in output)
    cnt["any_descriptive"]=sum(x["descriptive_factor_count"]>0 for x in output)
    manifest=json.loads((site/"factor_readiness_28a.json").read_text(encoding="utf-8"))
    manifest_ids=[f["id"] for f in manifest.get("factors",[])]
    if manifest_ids!=list(FACTOR_IDS) or not all(f.get("status")=="not_verified" for f in manifest["factors"]):
        raise ValueError("12-factor contract changed; refuse to publish a misleading readiness matrix")
    meta={
       "version":"2.9E","generated_at_taipei":dt.datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
       "model":"TPE-MFDS original M1-M3 I1-I3 F1-F3 S1-S3; two engines A/B",
       "macro_observation_status":macro.get("status",{}),
       "macro_publication_dates_verified":False,
       "industry_inventory_and_cycle_verified":False,
       "policy_event_to_company_impact_verified":False,
       "F2_peer_valuation_and_expectations_verified":False,
       "F3_governance_quality_verified":False,
       "retail_investor_sentiment_verified":False,
       "credit_balance_observations_not_retail_ownership":True,
       "stocks":len(output),"basic_qualified":cnt["base_qualified"],
       "snapshots_with_archives_later_than_price":cnt["source_postdates_price"],
       "stocks_with_some_descriptive_observation":cnt["any_descriptive"],
       "per_factor":factor_counts,
       "initial_min_price_sessions":MIN_PRICE_DAYS,"min_20d_average_turnover_twd":MIN_TURNOVER,
       "minimum_factor_coverage_initial":0.60,"production_target_coverage":0.75,
       "count_verified_factors":0,"model_eligible_stocks":0,
       "model_scores_enabled":False,"performance_probabilities_enabled":False,
       "point_in_time_publications_verified":False,
       "ordinary_stock_security_type_independently_verified":False,
       "session_calendar_independently_verified":False,
       "raw_close_corporate_actions_adjusted":False,
       "notes":[
         "observed_factor_count 只代表部分或描述性原始資料覆蓋，不是可建模或合格因子數，不能用它判斷60%門檻",
         "基本資格使用120個不同日期有效收盤、最近20個資料點成交額均值≥3000萬且收盤歷史日期對齊快照；未另外獨立證明每一官方交易日均存在",
         "F2僅用官方股價估值比率與同市場同業同日期的中位數提供部分證據，缺盈餘預期差及公告時間，不是便宜或投資價值分數",
         "F3僅用董事長與總經理是否兼任的官方觀察提供部分證據，非治理良窳、股權衝突或合規評級",
         "I1只就官方半導體業24類且樣本與單月營收擴散率合格的個股提供部分原始證據；缺庫存和多期循環不得認證",
         "I2官方政策公告有來源不代表任一公司獲益，未逐股核對資格和影響之前因子保持無資料",
         "S2只使用日期已確認的官方融資融券餘額作為部分原始證據，非真正的散戶比例或逐股當沖率；不可給正式情緒分數",
         "M1國發會最新景氣觀察為描述性來源，M2海關出口YoY及外銷訂單家數動向指數不是訂單金額YoY，M3央行匯率不等於完整市場外資動向",
         "宏觀資料所屬統計月份／日不代表當日已公開，國發會歷史資料可能回溯修訂；不得用於點時回測",
         "source_postdates_price 是首次封存時間晚於價格基準日的警示，不替代公司實際公告時間",
         "任何缺官方來源公布時點、除權息、OHLC或回測獨立性時，不輸出分數、報酬、勝率或10/20/60日概率"
       ]
    }
    (site/"factor_evidence_meta_29a.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return output,meta

if __name__=="__main__":
    rows,meta=build()
    print("2.9A per-stock original factor coverage",len(rows),"basic-qualified",meta["basic_qualified"],
          "verified factors",meta["count_verified_factors"])
