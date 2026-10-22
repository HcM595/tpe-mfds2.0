#!/usr/bin/env python3
"""TPE-MFDS 2.4D: source-provenanced TWSE market calendar, fail closed.

Does NOT generate dividend-adjusted OHLC, returns, backtest scores or fills.
TWSE holidaySchedule source is authoritative for the TWSE market ONLY. The
same schedule is a separately-labelled provisional reference for TPEx until
independently machine-verified against TPEx's own official calendar.
Preserve all distinct official-source versions; never backdate when observed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).resolve().parents[1]
DATA=BASE/'site'/'data'
URL='https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule'
TWSE_OFFICIAL='https://www.twse.com.tw/zh/trading/holiday.html'
TPEX_OFFICIAL='https://www.tpex.org.tw/zh-tw/announce/market/holiday.html'
EXRIGHT='https://www.twse.com.tw/zh/announcement/ex-right/twt49u.html'
UTC=dt.timezone.utc
TZ=ZoneInfo('Asia/Taipei')


def iso_utc(t):
    return t.astimezone(UTC).isoformat(timespec='microseconds').replace('+00:00','Z')


def roc_date(s):
    s=str(s).strip()
    if not re.fullmatch(r'\d{7}',s):
        raise ValueError('假日來源日期格式不是民國7碼：'+s[:30])
    return dt.date(int(s[:3])+1911,int(s[3:5]),int(s[5:])).isoformat()


def parse_holidays(raw):
    """Record exact official events. Only explicit *start/end trading* notices open."""
    if not isinstance(raw,list) or len(raw)<15 or len(raw)>100:
        raise ValueError('官方行事曆資料筆數異常')
    seen=set(); events=[]; years=set()
    for rec in raw:
        if not isinstance(rec,dict):raise ValueError('官方行事曆資料結構異常')
        date=roc_date(rec.get('Date',''))
        if date in seen:raise ValueError('官方行事曆重複日期：'+date)
        seen.add(date); years.add(int(date[:4]))
        name=str(rec.get('Name','')).strip()
        if not name:raise ValueError('官方事件名稱缺失')
        special_trade=any(x in name for x in ('開始交易日','最後交易日'))
        events.append({'date':date,'name':name,'non_trading':not special_trade})
    if len(years)!=1:raise ValueError('官方年度行事曆混有不同年份')
    year=next(iter(years))
    closed=sorted(x['date'] for x in events if x['non_trading'])
    if len(closed)<12:raise ValueError('官方休市日數不足')
    return year,sorted(events,key=lambda x:x['date']),closed


def load_json(p):
    obj=json.loads(p.read_text(encoding='utf-8-sig'))
    if not isinstance(obj,dict):raise ValueError('JSON格式錯誤：'+str(p))
    return obj


def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def get_official_json():
    req=urllib.request.Request(URL,headers={'User-Agent':'MFDS-Educational-Calendar/2.4D','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as resp:
        if resp.status!=200:raise RuntimeError('官方來源HTTP '+str(resp.status))
        data=resp.read(160_000)
    return json.loads(data.decode('utf-8-sig'))


def run(data_dir=DATA,now=None,fetcher=None,fixture=None):
    data_dir=Path(data_dir)
    now=now or dt.datetime.now(UTC)
    if now.tzinfo is None:raise ValueError('執行時間必須含時區')
    now=now.astimezone(UTC)
    current=now.astimezone(TZ).year
    root=data_dir/'official_calendar_sources'
    versions=[]
    for p in sorted(root.glob('year_*.json')):
        try:
            obj=load_json(p)
            can=json.dumps({'year':obj.get('year'),'events':obj.get('events'),
                            'closed_dates':obj.get('closed_dates')},ensure_ascii=False,
                            sort_keys=True,separators=(',',':')).encode('utf-8')
            if (obj.get('sha256')==p.stem.rsplit('_',1)[-1] and
                hashlib.sha256(can).hexdigest()==obj['sha256'] and
                isinstance(obj.get('closed_dates'),list)):
                versions.append(obj)
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError):
            pass
    fetch_error=None; selected_new=False
    try:
        raw=json.loads(Path(fixture).read_text(encoding='utf-8')) if fixture else (fetcher or get_official_json)()
        year,events,closed=parse_holidays(raw)
        # OpenAPI serves only its current published annual calendar; a stale
        # cross-year response must never be stamped with the present year.
        if year!=current:raise ValueError(f'官方來源年度{year}與目前{current}不同，拒絕冒用')
        canonical=json.dumps({'year':year,'events':events,'closed_dates':closed},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        sha=hashlib.sha256(canonical).hexdigest()
        dest=root/f'year_{year}_{sha}.json'
        matches=[v for v in versions if v.get('sha256')==sha and v.get('year')==year]
        if matches:
            captured=matches[0]
        else:
            if dest.exists():raise ValueError('官方曆資料檔存在但未通過內容檢查，拒絕覆寫')
            captured={'year':year,'events':events,'closed_dates':closed,'sha256':sha,
                      'source_first_seen_utc':iso_utc(now),'source_url':URL,
                      'source_role':'TWSE_官方開休市日期；TPEx僅作參考'}
            dump(dest,captured)
            versions.append(captured)
            selected_new=True
    except (Exception,) as exc:
        fetch_error=f'{type(exc).__name__}: {str(exc)[:160]}'
    # Current year usable only if there is an immutable, validated source record.
    matches=[v for v in versions if v.get('year')==current]
    latest=max(matches,key=lambda v:v.get('source_first_seen_utc','')) if matches else None
    usable=bool(latest and len(latest.get('closed_dates',[]))>=12)
    out={'version':'2.4D','generated_at_taipei':now.astimezone(TZ).isoformat(timespec='seconds'),
         'status':'ok' if usable else 'unavailable_fail_closed',
         'calendar_year':current,'new_source_version_saved':selected_new,
         'twse_source_url':URL,'twse_official_info_url':TWSE_OFFICIAL,
         'tpex_official_info_url':TPEX_OFFICIAL,
         'markets':{'上市':'TWSE官方休市表＋行情覆蓋度交叉確認' if usable else '無已核實官方休市表，不計數',
                    '上櫃':'採用TWSE官方休市表作參考；尚未獨立機器驗證TPEx休市表' if usable else '無已核實官方休市表，不計數'},
         'years':{},'download_error':fetch_error,
         'calendar_still_needs':'交易所臨時停市、個股暫停交易、官方TPEx獨立行事曆仍需核實',
         'corporate_action_readiness':{
             'twse_exright_reference_url':EXRIGHT,
             'twse_corporate_actions_ingested':False,
             'tpex_corporate_actions_ingested':False,
             'verified_adjusted_ohlc':False,
             'verified_cash_dividends':False,
             'total_return_calculation_allowed':False,
             'note':'除權息參考價並非含現金股利的總報酬。官方事件尚未完成全期間蒐集、核對與調整，不製作還原OHLC或報酬。'},
         'performance_metrics_enabled':False}
    by_year={}
    for v in versions:
        y=v['year']
        if y not in by_year or v.get('source_first_seen_utc','')>by_year[y].get('source_first_seen_utc',''):
            by_year[y]=v
    for y,v in sorted(by_year.items()):
        out['years'][str(y)]={'status':'twse_official_verified',
                              'closed_dates':v['closed_dates'],
                              'source_first_seen_utc':v['source_first_seen_utc'],
                              'source_sha256':v['sha256'],
                              'source_file':f'official_calendar_sources/year_{y}_{v["sha256"]}.json',
                              'official_events_count':len(v['events'])}
    dump(data_dir/'official_session_calendar.json',out)
    print('2.4D official calendar:',out['status'], 'year',current,'closed',len(out['years'].get(str(current),{}).get('closed_dates',[])), 'NO RETURNS')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir',type=Path,default=DATA)
    p.add_argument('--holiday-fixture',type=Path)
    args=p.parse_args();run(args.data_dir,fixture=args.holiday_fixture)
