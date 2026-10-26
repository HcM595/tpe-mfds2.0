#!/usr/bin/env python3
"""2.9B Official NDC monthly economic signals and CBC interbank USD/TWD closes.

Observations are not publication timestamps or verified point-in-time factors.
Historical NDC economic series can be revised; archives preserve fetched versions.
Failed providers keep their own previous snapshot, visibly marked stale.
No model score, market timing, 10/20/60d probability or trade recommendation.
"""
import csv,datetime as dt,hashlib,io,json,math,urllib.parse,urllib.request,zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
NDCDOC="https://data.gov.tw/api/v2/rest/dataset/6099"
CBCURL="https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day"
NDCCOLS=["period","light","signal_score","export_ntd_billion",
         "export_yoy_pct","export_order_direction_index"]
FXCOLS=["date","usd_twd_close"]
LIGHTS={"藍","黃藍","綠","黃紅","紅"}
def get(url,max_bytes=8_000_000):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 TPE-MFDS official-macro-research",
                                            "Accept":"application/json,application/zip,text/csv,*/*"})
    with urllib.request.urlopen(req,timeout=35) as response:
        blob=response.read(max_bytes+1)
    if len(blob)>max_bytes:raise ValueError("official source exceeds bounded download size")
    return blob
def ndc_resource_url(meta):
    record=meta.get("result") if isinstance(meta,dict) else None
    if not isinstance(record,dict):raise ValueError("invalid NDC dataset metadata")
    sources=record.get("distribution")
    if not isinstance(sources,list):raise ValueError("NDC distribution missing")
    options=[r.get("resourceDownloadUrl","") for r in sources
             if r.get("resourceFormat","").upper()=="ZIP" and isinstance(r,dict)]
    for u in options:
        parsed=urllib.parse.urlsplit(u)
        if parsed.scheme=="https" and parsed.hostname=="ws.ndc.gov.tw" and parsed.path=="/Download.ashx":
            return u
    raise ValueError("no whitelisted official NDC ZIP resource")
def number(v):
    try:
        if v is None or str(v).strip() in ("","-","--","NA","N/A"):return None
        n=float(str(v).strip().replace(",",""))
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None
def csv_member(archive,name):
    members=[x for x in archive.infolist() if x.filename==name and not x.is_dir()]
    if len(members)!=1 or members[0].file_size>2_000_000:raise ValueError("NDC expected bounded CSV missing")
    raw=archive.read(members[0]).decode("utf-8-sig")
    data=list(csv.DictReader(io.StringIO(raw)))
    if not data:raise ValueError("NDC empty CSV: "+name)
    return data
def parse_ndc_zip(raw,now):
    if len(raw)>8_000_000:raise ValueError("NDC ZIP too large")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.infolist())>40 or sum(x.file_size for x in z.infolist())>9_000_000:
            raise ValueError("NDC ZIP structure exceeds limits")
        signal=csv_member(z,"景氣指標與燈號.csv")
        simultaneous=csv_member(z,"同時指標構成項目.csv")
        leading=csv_member(z,"領先指標構成項目.csv")
    def row_index(rows,required):
        if not set(required).issubset(rows[0]):raise ValueError("NDC expected fields missing")
        return {r["Date"]:r for r in rows if len(str(r.get("Date","")))==6
                and str(r.get("Date","")).isdigit()}
    ss=row_index(signal,["Date","景氣對策信號綜合分數","景氣對策信號"])
    xx=row_index(simultaneous,["Date","海關出口值(十億元)"])
    oo=row_index(leading,["Date","外銷訂單動向指數(以家數計)"])
    out=[]
    for period in sorted(ss):
        try:
            year,month=int(period[:4]),int(period[4:])
            date=dt.date(year,month,1)
            if date>now.replace(day=1):continue
        except ValueError:continue
        score=number(ss[period].get("景氣對策信號綜合分數"))
        light=str(ss[period].get("景氣對策信號","")).strip()
        export=number(xx.get(period,{}).get("海關出口值(十億元)"))
        orders=number(oo.get(period,{}).get("外銷訂單動向指數(以家數計)"))
        if not ((score is not None and score>=9 and score<=45 and light in LIGHTS) or export is not None or orders is not None):
            continue
        prior=str(year-1)+f"{month:02d}"
        earlier=number(xx.get(prior,{}).get("海關出口值(十億元)"))
        yoy=(round((export/earlier-1)*100,4) if export is not None and
             earlier is not None and earlier>0 else "")
        out.append(dict(period=period,light=light if score is not None and 9<=score<=45 and light in LIGHTS else "",
                        signal_score=score if score is not None and 9<=score<=45 and light in LIGHTS else "",
                        export_ntd_billion=export if export is not None and export>=0 else "",
                        export_yoy_pct=yoy,
                        export_order_direction_index=orders if orders is not None else ""))
    if len(out)<40:raise ValueError("NDC observations too sparse")
    return out
def parse_cbc_json(raw,now):
    entries=json.loads(raw.decode("utf-8-sig"))
    if not isinstance(entries,list) or not entries or not isinstance(entries[0],dict):
        raise ValueError("CBC daily response not a list")
    if not {"日期","NTD_USD"}.issubset(entries[0]):raise ValueError("CBC unexpected daily schema")
    bydate={}
    for item in entries:
        date=str(item.get("日期",""))
        if len(date)!=8 or not date.isdigit():continue
        try:d=dt.date(int(date[:4]),int(date[4:6]),int(date[6:]))
        except ValueError:continue
        v=number(item.get("NTD_USD"))
        if d>now or v is None or not (5<v<100):continue
        bydate[d.isoformat()]=round(v,5)
    if len(bydate)<100:raise ValueError("CBC history too sparse")
    return [{"date":date,"usd_twd_close":value} for date,value in sorted(bydate.items())]
def keep_archive(folder,raw,suffix,now):
    sha=hashlib.sha256(raw).hexdigest()
    blob=folder/(sha+suffix);seen=folder/(sha+".first_seen")
    folder.mkdir(parents=True,exist_ok=True)
    if not blob.is_file():
        blob.write_bytes(raw)
        seen.write_text(now.isoformat(timespec="seconds")+"\n",encoding="utf-8")
    return sha,seen.read_text(encoding="utf-8").strip() if seen.is_file() else ""
def write_csv(path,fields,rows):
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
        w.writeheader();w.writerows(rows)
def read_csv(path):
    if not path.is_file():return []
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def collect(root=ROOT,fetch=get,clock=None):
    clock=clock or dt.datetime.now(dt.timezone.utc)
    today=clock.astimezone(ZoneInfo("Asia/Taipei")).date()
    data=root/"site"/"data"; data.mkdir(parents=True,exist_ok=True)
    archive=root/"history_data"/"macro_sources"
    prior=data/"macro_snapshot_29b.json"
    prev=json.loads(prior.read_text(encoding="utf-8")) if prior.is_file() else {}
    records={}
    for key,resource in (("ndc","macro_ndc_history_29b.csv"),("cbc","macro_fx_history_29b.csv")):
        records[key]=read_csv(data/resource)
    status={};origin={}
    try:
        doc=json.loads(fetch(NDCDOC).decode("utf-8-sig"))
        url=ndc_resource_url(doc)
        raw=fetch(url)
        rows=parse_ndc_zip(raw,today)
        sha,seen=keep_archive(archive/"ndc",raw,".zip",clock)
        write_csv(data/"macro_ndc_history_29b.csv",NDCCOLS,rows)
        records["ndc"]=rows
        status["ndc"]="ok";origin["ndc"]={"source_url":url,"sha256":sha,"first_seen_utc":seen}
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,zipfile.BadZipFile,json.JSONDecodeError) as e:
        status["ndc"]="stale_backup" if records["ndc"] else "unavailable"
        origin["ndc"]=dict(prev.get("sources",{}).get("ndc") or {},error=str(e)[:210])
    try:
        raw=fetch(CBCURL)
        rows=parse_cbc_json(raw,today)
        sha,seen=keep_archive(archive/"cbc",raw,".json",clock)
        write_csv(data/"macro_fx_history_29b.csv",FXCOLS,rows)
        records["cbc"]=rows
        status["cbc"]="ok";origin["cbc"]={"source_url":CBCURL,"sha256":sha,"first_seen_utc":seen}
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError) as e:
        status["cbc"]="stale_backup" if records["cbc"] else "unavailable"
        origin["cbc"]=dict(prev.get("sources",{}).get("cbc") or {},error=str(e)[:210])
    ndc=records["ndc"];fx=records["cbc"]
    last_ndc=ndc[-1] if ndc else {}
    signal=next((r for r in reversed(ndc) if number(r.get("signal_score")) is not None and r.get("light")), {})
    export=next((r for r in reversed(ndc) if number(r.get("export_ntd_billion")) is not None),{})
    order=next((r for r in reversed(ndc) if number(r.get("export_order_direction_index")) is not None),{})
    fxlast=fx[-1] if fx else {}
    change20=(round((number(fx[-1]["usd_twd_close"])/number(fx[-21]["usd_twd_close"])-1)*100,4)
              if len(fx)>=21 and number(fx[-21]["usd_twd_close"]) and number(fx[-1]["usd_twd_close"]) else None)
    view={"version":"2.9B","generated_at_taipei":clock.astimezone(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
          "sources":origin,"status":status,
          "M1":{"observation_period":signal.get("period",""),"light":signal.get("light",""),
                "composite_score":signal.get("signal_score",""),
                "published_at":None,"readiness":"official_observation_not_pit_verified" if signal else "unavailable"},
          "M2":{"export_period":export.get("period",""),
                "export_ntd_billion":export.get("export_ntd_billion",""),
                "export_yoy_pct":export.get("export_yoy_pct",""),
                "order_direction_period":order.get("period",""),
                "order_direction_index":order.get("export_order_direction_index",""),
                "published_at":None,
                "export_orders_amount_yoy_verified":False,
                "readiness":"partial_not_model_verified" if export or order else "unavailable"},
          "M3":{"exchange_close_date":fxlast.get("date",""),
                "usd_twd_close":fxlast.get("usd_twd_close",""),
                "usd_twd_20obs_change_pct":change20,
                "published_at":None,
                "market_wide_foreign_flow_verified":False,
                "readiness":"partial_not_model_verified" if fxlast else "unavailable"},
          "records":{"ndc":len(ndc),"cbc":len(fx)},
          "factor_scores_enabled":False,"backtest_enabled":False,"probability_enabled":False,
          "notes":["景氣及出口數據是所屬統計月份，不是公告日期；國發會歷史數列可能被回溯修訂",
                   "外銷訂單動向指數（以家數計）不等於外銷訂單金額YoY，M2因子尚未完備",
                   "USD/TWD匯率是新台幣每1美元，20筆觀察間變化不是模型因子得分",
                   "官方月資料與日資料不能因為已下載就視為當時已知，沒有獨立公告時間與回測驗證不得預測"]}
    prior.write_text(json.dumps(view,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return records,view

if __name__=="__main__":
    values,meta=collect()
    print("2.9B macro feeds",meta["status"],"records",meta["records"],
          "M1",meta["M1"]["observation_period"],"FX",meta["M3"]["exchange_close_date"])
