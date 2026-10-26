#!/usr/bin/env python3
"""2.9D: same-market same-sector official-revenue diffusion and bounded history.

ONE revenue month yields a cross-sectional breadth observation, NOT a measured
industry cycle. TWSE/TPEx classifications are not pooled across exchanges.
No inventory turnover, per-company announcement times, policy effects, signal
score, backtest or probability is invented.
"""
import csv,datetime as dt,hashlib,json,math,statistics
from collections import Counter,defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).resolve().parents[1]
MIN_PEERS=5
MIN_COVERAGE=.6
HIST=["stock_id","stock_name","market","sector","period","yoy_pct","mom_pct",
      "revenue_thousand_twd","table_date","source_sha256","first_seen_utc",
      "per_company_filing_time_verified"]
SECTOR=["market","sector","period","members_in_master","observed_peers","observed_share",
        "positive_yoy_peers","negative_yoy_peers","zero_yoy_peers","growth_diffusion_pct",
        "median_yoy_pct","median_mom_pct","has_three_months","has_inventory_evidence",
        "cycle_phase_verified","factor_I1_eligible","status"]
STOCK=["stock_id","stock_name","market","sector","period","table_date",
       "stock_yoy_pct","industry_peers","industry_members","observed_share",
       "growth_diffusion_pct","industry_median_yoy_pct","industry_median_mom_pct",
       "historical_months_this_stock","three_month_history","inventory_verified",
       "cycle_phase_verified","factor_I1_eligible","status"]
def read(path):
    if not path.exists():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def write(path,columns,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore",lineterminator="\n")
        wr.writeheader();wr.writerows(rows)
def val(v):
    try:
        if v is None or str(v).strip()=="":return None
        n=float(str(v).replace(",",""))
        return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None
def month(s):
    s=str(s or "")
    if len(s)!=7 or s[4]!="-":return False
    try:return dt.date.fromisoformat(s+"-01").strftime("%Y-%m")==s
    except ValueError:return False
def date(s):
    try:return dt.date.fromisoformat(str(s)).isoformat()==str(s)
    except ValueError:return False
def compute(master,revenue,old_history=(),today=None):
    today=today or dt.date.today()
    companies={(r["stock_id"],r["market"]):r for r in master
               if r.get("stock_id") and r.get("market") in ("上市","上櫃") and r.get("sector")}
    membership=Counter((market,row["sector"]) for (_,market),row in companies.items())
    old={(r["stock_id"],r["market"],r["period"]):dict(r) for r in old_history
         if r.get("stock_id") and r.get("market") and month(r.get("period"))}
    revisions=[]
    valid={}
    skipped=Counter()
    for r in revenue:
        stock=str(r.get("stock_id",""))
        market=r.get("market","")
        co=companies.get((stock,market))
        period=r.get("revenue_period","")
        table_date=r.get("table_date","")
        yoy=val(r.get("month_revenue_yoy_pct"))
        mom=val(r.get("month_revenue_mom_pct"))
        rev=val(r.get("month_revenue_thousand_twd"))
        if not co:
            skipped["missing_master_sector_or_market"]+=1;continue
        if not month(period) or not date(table_date) or period>today.strftime("%Y-%m") or table_date>today.isoformat():
            skipped["bad_or_future_month_or_table_date"]+=1;continue
        if rev is None or rev<0:
            skipped["invalid_revenue"]+=1;continue
        if yoy is None:
            skipped["missing_yoy"]+=1;continue
        k=(stock,market,period)
        if k in valid:
            skipped["duplicate_stock_period"]+=1;continue
        record=dict(stock_id=stock,stock_name=r.get("stock_name",""),
                    market=market,sector=co["sector"],period=period,
                    yoy_pct=round(yoy,4),mom_pct=round(mom,4) if mom is not None else "",
                    revenue_thousand_twd=rev,table_date=table_date,
                    source_sha256=r.get("source_sha256",""),
                    first_seen_utc=r.get("first_seen_utc",""),
                    per_company_filing_time_verified="false")
        valid[k]=record
        if k not in old:old[k]=record
        else:
            previous=old[k]
            if any(str(previous.get(c,""))!=str(record.get(c,"")) for c in
                   ("yoy_pct","mom_pct","revenue_thousand_twd")):
                revisions.append({
                    "stock_id":stock,"market":market,"period":period,
                    "previous_source_sha256":previous.get("source_sha256",""),
                    "observed_source_sha256":record["source_sha256"],
                    "detected_on":today.isoformat(),"change_status":"revision_requires_separate_point_in_time_validation"})
    years=defaultdict(set)
    for r in old.values():years[(r["stock_id"],r["market"])].add(r["period"])
    groups=defaultdict(list)
    for r in valid.values():groups[(r["market"],r["sector"],r["period"])].append(r)
    latest={}
    for k in groups:
        x=k[:2]
        if x not in latest or k[2]>latest[x]:latest[x]=k[2]
    sectors=[];stock_rows=[]
    for (market,sector),period in sorted(latest.items()):
        peers=groups[(market,sector,period)]
        yoy=[val(r["yoy_pct"]) for r in peers]
        yoy=[v for v in yoy if v is not None]
        mon=[val(r.get("mom_pct")) for r in peers]
        mon=[v for v in mon if v is not None]
        members=membership[(market,sector)]
        sample=len(peers)
        coverage=sample/members if members else 0
        full=sample>=MIN_PEERS and coverage>=MIN_COVERAGE
        pos=sum(v>0 for v in yoy)
        neg=sum(v<0 for v in yoy)
        zero=sum(v==0 for v in yoy)
        breadth=round(100*pos/sample,2) if full else ""
        median=round(statistics.median(yoy),4) if full else ""
        mom=round(statistics.median(mon),4) if full and len(mon)>=MIN_PEERS else ""
        historical_months=max((len(years[(r["stock_id"],market)]) for r in peers),default=0)
        # This is *not* a claim that all firms have 3 months of synchronized revenue.
        enough_months=all(len(years[(r["stock_id"],market)])>=3 for r in peers)
        sec=dict(market=market,sector=sector,period=period,
          members_in_master=members,observed_peers=sample,observed_share=round(coverage,4),
          positive_yoy_peers=pos,negative_yoy_peers=neg,zero_yoy_peers=zero,
          growth_diffusion_pct=breadth,median_yoy_pct=median,
          median_mom_pct=mom,has_three_months=str(enough_months).lower(),
          has_inventory_evidence="false",cycle_phase_verified="false",
          factor_I1_eligible="false",
          status="單月描述性產業營收擴散率（未核對個別公告日）" if full else "同產業樣本過少或覆蓋不足")
        sectors.append(sec)
        for r in peers:
            stock_rows.append(dict(stock_id=r["stock_id"],stock_name=r["stock_name"],
              market=market,sector=sector,period=period,table_date=r["table_date"],
              stock_yoy_pct=r["yoy_pct"],industry_peers=sample,industry_members=members,
              observed_share=round(coverage,4),growth_diffusion_pct=breadth,
              industry_median_yoy_pct=median,industry_median_mom_pct=mom,
              historical_months_this_stock=len(years[(r["stock_id"],market)]),
              three_month_history=str(len(years[(r["stock_id"],market)])>=3).lower(),
              inventory_verified="false",cycle_phase_verified="false",
              factor_I1_eligible="false",status=sec["status"]))
    return (sorted(stock_rows,key=lambda r:(r["market"],r["stock_id"])),
            sectors,sorted(old.values(),key=lambda r:(r["market"],r["stock_id"],r["period"])),
            revisions,dict(skipped))
def build(base=BASE,clock=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    today=clock.astimezone(ZoneInfo("Asia/Taipei")).date()
    site=base/"site"/"data"
    previous=read(site/"revenue_history_29d.csv")
    stock,sector,hist,revisions,skipped=compute(
      read(base/"history_data"/"ordinary_stock_master.csv"),
      read(site/"revenue_snapshot_28c.csv"),previous,today)
    write(site/"revenue_history_29d.csv",HIST,hist)
    write(site/"industry_breadth_29d.csv",STOCK,stock)
    write(site/"industry_sector_breadth_29d.csv",SECTOR,sector)
    revision_dest=site/"revenue_revision_flags_29d.csv"
    prior_rev=read(revision_dest)
    keys={(r.get("stock_id"),r.get("market"),r.get("period"),r.get("observed_source_sha256")) for r in prior_rev}
    prior_rev.extend(r for r in revisions if (r["stock_id"],r["market"],r["period"],r["observed_source_sha256"]) not in keys)
    if prior_rev or revisions:
        write(revision_dest,["stock_id","market","period","previous_source_sha256","observed_source_sha256","detected_on","change_status"],prior_rev)
    strong=sum(bool(r["growth_diffusion_pct"]!="") for r in sector)
    semis=[r for r in sector if r["sector"]=="24"]
    meta={
      "version":"2.9D","generated_at_taipei":clock.astimezone(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
      "stock_rows":len(stock),"sector_groups":len(sector),"usable_single_month_groups":strong,
      "revenue_archive_rows":len(hist),"revision_flags":len(prior_rev),
      "semiconductor_market_groups":len(semis),
      "semi_group_breadth_descriptive":sum(x["growth_diffusion_pct"]!="" for x in semis),
      "min_peers":MIN_PEERS,"min_sector_coverage":MIN_COVERAGE,
      "period_history_3_month_verified":False,"industry_inventory_verified":False,
      "industry_cycle_stage_verified":False,"I1_factor_eligible":False,
      "policy_impact_not_inferred_from_industry":True,
      "excluded":skipped,
      "notes":["同一市場＋官方公司名錄產業代碼分組；不同市場不可直接混加",
               "只用最新官方月營收快照計算同一月份的正成長個股家數／有數據家數；至少5股且覆蓋同產業名錄至少60%才顯示擴散率",
               "正成長占比是單月橫斷面；仍缺完整連續月度樣本及企業存貨變化，不是半導體週期階段或股價預測",
               "月營收表出表日不是個別公司申報日；多次下載首次封存不可當歷史公布時點",
               "月營收歷史從本站實際封存開始增長；舊數列若修訂只保留觀察與審核標記，不悄悄覆寫首次來源"]}
    (site/"industry_cycle_meta_29d.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("2.9D industry growth breadth",len(stock),"stocks",len(sector),"sectors",strong,"qualified descriptive groups")
    return stock,sector,meta
if __name__=="__main__":build()
