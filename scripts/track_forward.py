#!/usr/bin/env python3
"""TPE-MFDS 2.4C: immutable prospective research cohorts and observation progress.

No buying/selling recommendation. No returns are calculated, because the current
price_history.csv has unadjusted CLOSE only, not verified adjusted OHLC, corporate
actions or an independently authenticated market-session calendar.

* Cohorts are registered only *now*, never backdated to an earlier source date.
* Each unique archived signal fingerprint is frozen into an immutable cohort.
* 2.4B's per-security audit status is frozen when that cohort is created.
* Multiple workflow re-runs of the same fingerprint never add cohorts/samples.
* 10/20/60 horizons count conservatively from the *first eligible later market
  session* using currently covered history, and are status-only observations.
* Nothing is represented as a trade fill or realized/total return.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'site' / 'data'
TZ = ZoneInfo('Asia/Taipei')
UTC = dt.timezone.utc
VERSION = '2.4C'
HORIZONS = (10, 20, 60)
MIN_MARKET_SYMBOLS = 100
CSV_COLS = [
    'cohort_id','stock_id','stock_name','market','signal_price_asof',
    'signal_first_observed_at_utc','cohort_registered_at_utc',
    'observation_status','audit_flags','chip_strength_rank',
    'chip_strength_score','technical_confirmed_count','technical_status',
    'holder_structure','reference_session',
    'h10_observed_sessions','h10_target_session','h10_status',
    'h20_observed_sessions','h20_target_session','h20_status',
    'h60_observed_sessions','h60_target_session','h60_status',
    'performance_status','note'
]
ISSUE_COLS = ['cohort_id','stock_id','stock_name','issue_type','description']


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def utc_time(value):
    try:
        result = dt.datetime.fromisoformat(str(value).strip().replace('Z','+00:00'))
        return result.astimezone(UTC) if result.tzinfo else None
    except (ValueError, TypeError):
        return None


def day(value):
    try: return dt.date.fromisoformat(str(value).strip())
    except (ValueError, TypeError): return None


def zulu(value):
    return value.astimezone(UTC).isoformat(timespec='microseconds').replace('+00:00','Z')


def load_json(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict): raise ValueError('JSON格式不正確：'+str(path))
    return value


def load_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:raise ValueError('CSV欄位不存在：'+str(path))
        return list(reader)


def write_json(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    # Deterministic, immutable encoding for hash checks.
    raw = (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    path.write_bytes(raw)
    return digest(raw)


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=cols,extrasaction='ignore')
        writer.writeheader();writer.writerows(rows)


def norm_market(value):
    s=str(value or '').strip()
    if s not in ('上市','上櫃'):
        raise ValueError('無效市場別：'+str(value))
    return s


def valid_source(data_dir, now):
    """Require 2.4A+2.4B agreement, original archived snapshot checksum and fresh audit."""
    idx = load_json(data_dir/'signal_archive_index.json')
    entries = idx.get('snapshots')
    if not isinstance(entries,list) or not entries or idx.get('snapshots_total')!=len(entries):
        raise ValueError('2.4A歷史快照索引不完整')
    ids={}
    for e in entries:
        if not isinstance(e,dict) or e.get('snapshot_id') in ids:
            raise ValueError('歷史快照編號重複或格式錯誤')
        ids[e['snapshot_id']]=e
    latest=max(entries,key=lambda e:(utc_time(e.get('captured_at_utc')) or dt.datetime.min.replace(tzinfo=UTC),e['snapshot_id']))
    actual_path=(data_dir/str(latest.get('snapshot_path',''))).resolve()
    archive_root=(data_dir/'signal_archive').resolve()
    if not actual_path.is_relative_to(archive_root) or actual_path.name!='snapshot.json':
        raise ValueError('不安全的來源快照路徑')
    if not actual_path.is_file() or digest(actual_path.read_bytes())!=latest.get('snapshot_sha256'):
        raise ValueError('2.4A快照不存在或SHA-256不符')
    snap=load_json(actual_path)
    if utc_time(snap.get('captured_at_utc')) is None or utc_time(snap['captured_at_utc'])>now+dt.timedelta(minutes=5):
        raise ValueError('2.4A快照時間不存在或落在未來')
    if snap.get('snapshot_id')!=latest.get('snapshot_id') or snap.get('signal_fingerprint')!=latest.get('signal_fingerprint'):
        raise ValueError('來源訊號指紋與索引不一致')
    if snap.get('source_published_at') not in (None,''):
        raise ValueError('來源公告時間未核實，禁止回填')
    if not isinstance(snap.get('signals'),list):
        raise ValueError('來源快照缺逐檔訊號')
    first_id=latest.get('first_seen_snapshot_id') or latest['snapshot_id']
    if first_id not in ids or ids[first_id].get('signal_fingerprint')!=latest['signal_fingerprint']:
        raise ValueError('來源首次觀測快照與訊號指紋不一致')
    first_seen=utc_time(ids[first_id].get('captured_at_utc'))
    if first_seen is None or first_seen > now:
        raise ValueError('首次封存時間不合理')
    audit=load_json(data_dir/'pit_audit_meta.json')
    if audit.get('version')!='2.4B' or audit.get('status')!='ok':
        raise ValueError('2.4B稽核報告未成功完成')
    if audit.get('audited_snapshot_id')!=snap.get('snapshot_id'):
        raise ValueError('2.4B稽核快照與最新2.4A封存不一致')
    if audit.get('first_seen_snapshot_id')!=first_id:
        raise ValueError('2.4B首次封存指向與2.4A不一致')
    if utc_time(audit.get('signal_first_observed_at_utc'))!=first_seen:
        raise ValueError('2.4B訊號首次觀測時間與2.4A不一致')
    audit_generated=utc_time(audit.get('generated_at_taipei'))
    if audit_generated is None or audit_generated > now+dt.timedelta(minutes=5) or now-audit_generated>dt.timedelta(hours=5):
        raise ValueError('2.4B稽核報告非當次新資料，拒絕建立新觀察名單')
    rows=load_csv(data_dir/'pit_audit.csv')
    if len(rows)!=audit.get('candidate_rows') or len(rows)!=len(snap['signals']):
        raise ValueError('2.4B逐檔報告與來源快照筆數不一致')
    byid={}
    for r in rows:
        code=r.get('stock_id','').strip()
        if not re.fullmatch(r'[0-9A-Za-z]{4,8}',code) or code in byid:
            raise ValueError('2.4B股票代號不合法或重複')
        byid[code]=r
    source={r.get('stock_id'):r for r in snap['signals']}
    if len(source)!=len(rows) or set(source)!=set(byid):
        raise ValueError('2.4B逐檔股票池與封存內容不一致')
    for code,r in byid.items():
        s=source[code]
        for key in ('chip_strength_rank','chip_strength_score','rank_status','price_asof'):
            if str(s.get(key,'')).strip()!=str(r.get(key,'')).strip():
                raise ValueError(f'{code} 2.4B結果與歷史快照欄位不一致: {key}')
    if sum(r.get('rank_status')=='可排名' for r in rows)!=audit.get('eligible_ranked'):
        raise ValueError('2.4B有效排名數不一致')
    return idx,latest,snap,first_seen,rows,audit


def validate_cohort_registry(data_dir):
    root=(data_dir/'forward_cohorts').resolve()
    path=data_dir/'forward_cohorts_index.json'
    if not path.exists():
        if root.exists() and any(root.glob('*.json')):
            raise ValueError('觀察組索引遺失，但仍存在舊觀察組檔案')
        return {'version':VERSION,'cohorts':[],'cohorts_total':0},{}
    index=load_json(path)
    rows=index.get('cohorts',[])
    if index.get('version')!=VERSION or not isinstance(rows,list) or index.get('cohorts_total')!=len(rows):
        raise ValueError('觀察組歷史索引不完整')
    known={};ids=set()
    for item in rows:
        fp=str(item.get('signal_fingerprint',''))
        identity=str(item.get('cohort_id',''))
        if not re.fullmatch(r'[0-9a-f]{64}',fp) or fp in known or identity in ids:
            raise ValueError('觀察組訊號重複或格式錯誤')
        ids.add(identity)
        dest=(data_dir/str(item.get('cohort_path',''))).resolve()
        if not dest.is_relative_to(root) or dest.name!=identity+'.json' or not dest.is_file():
            raise ValueError('歷史觀察組缺檔或路徑異常')
        if digest(dest.read_bytes())!=item.get('cohort_sha256'):
            raise ValueError('歷史觀察組遭變更，SHA-256不一致')
        cohort=load_json(dest)
        if cohort.get('cohort_id')!=identity or cohort.get('signal_fingerprint')!=fp:
            raise ValueError('觀察組內容與索引不一致')
        if utc_time(cohort.get('registered_at_utc')) is None:
            raise ValueError('觀察組缺註冊時間')
        known[fp]=cohort
    if root.exists() and set(p.stem for p in root.glob('*.json')) != ids:
        raise ValueError('觀察組檔案與索引數量不符，不可靜默遺失舊組別')
    return index,known


def make_cohort(latest,snap,first_seen,rows,audit,now,audit_csv_sha256):
    fp=latest['signal_fingerprint']
    if not re.fullmatch(r'[0-9a-f]{64}',fp):
        raise ValueError('來源訊號指紋不合法')
    cohort_id='cohort-'+fp[:24]
    audit_rows=[]
    for r in sorted(rows,key=lambda x:x['stock_id']):
        status=r.get('forward_observation','')
        if status not in ('可前瞻觀察_仍需來源核實','暫緩_資料須核對','不列入_非有效排名'):
            raise ValueError('未知的2.4B前瞻觀察分類：'+status)
        if status=='可前瞻觀察_仍需來源核實' and (r.get('rank_status')!='可排名' or r.get('audit_flags')):
            raise ValueError('2.4B觀察資格標記衝突')
        audit_rows.append({key:r.get(key,'') for key in (
            'stock_id','stock_name','market','rank_status','price_asof','flow_asof',
            'holder_asof','chip_strength_rank','chip_strength_score','technical_status',
            'technical_confirmed_count','holder_structure','holder_anomaly_flag',
            'audit_flags','forward_observation','strict_historical_backtest',
            'five_day_flow_audit','four_week_holder_audit')})
    return {
        'version':VERSION,'cohort_id':cohort_id,'signal_fingerprint':fp,
        'registered_at_utc':zulu(now),'first_signal_observed_at_utc':zulu(first_seen),
        'source_snapshot_id':latest['snapshot_id'],
        'first_seen_snapshot_id':audit['first_seen_snapshot_id'],
        'source_price_dates':snap['summary'].get('source_price_dates',[]),
        'audit_snapshot_id':audit['audited_snapshot_id'],
        'audit_generated_at_taipei':audit['generated_at_taipei'],
        'audit_csv_sha256':audit_csv_sha256,
        'qualified_entries':sum(r['forward_observation']=='可前瞻觀察_仍需來源核實' for r in audit_rows),
        'entries':audit_rows,
        'rules':[
            '本觀察組首次登錄時間=2.4C實際執行時間，不能回填至較早來源交易日。',
            '一組訊號指紋只能建立一個不可覆寫的觀察組；重跑不增加獨立樣本。',
            '觀察起算以登錄日期嚴格之後的第一個完整市場交易日為參考日，絕非成交進場價。',
            '第10/20/60交易日為參考日之後第10/20/60個市場交易日。',
            '本版不計算或宣稱任何績效、勝率、交易價格或除權息報酬。'
        ],
    }


def market_sessions(data_dir, observation_cohorts, now, min_symbols=MIN_MARKET_SYMBOLS):
    """Coverage-based exchange-session proxy. Never call it an official calendar."""
    if not isinstance(min_symbols,int) or min_symbols<2:
        raise ValueError('市場交易日有效股票門檻不合法')
    latest_official=load_csv(data_dir/'official_snapshot.csv')
    mapping={}
    for row in latest_official:
        code=row.get('stock_id','').strip()
        market=str(row.get('market','')).strip()
        if code and market in ('上市','上櫃'):
            if code in mapping and mapping[code]!=market:raise ValueError('同代號不同市場，交易日曆不可混算')
            mapping[code]=market
    market_conflicts=set()
    for cohort in observation_cohorts:
        for item in cohort['entries']:
            code=item['stock_id']; market=norm_market(item['market'])
            if code in mapping and mapping[code]!=market:
                market_conflicts.add((cohort['cohort_id'],code))
            else:
                mapping[code]=market
    coverage=defaultdict(lambda:defaultdict(set))
    cutoff=now.astimezone(TZ).date()
    for row in load_csv(data_dir/'price_history.csv'):
        code=row.get('stock_id','').strip()
        market=mapping.get(code)
        d=day(row.get('date'))
        if market and d and d<=cutoff:
            try:
                close=float(row.get('close',''))
            except (TypeError, ValueError):continue
            if math.isfinite(close) and close>0:
                coverage[market][d].add(code)
    sessions={market:sorted(d for d,codes in coverage[market].items() if len(codes)>=min_symbols)
              for market in ('上市','上櫃')}
    return sessions, {market:len(sessions[market]) for market in sessions}, market_conflicts


def make_observations(cohorts,sessions,market_conflicts=None):
    market_conflicts=market_conflicts or set()
    records=[];issues=[]; counters={str(h):Counter() for h in HORIZONS}
    for cohort in sorted(cohorts,key=lambda c:(c['registered_at_utc'],c['cohort_id'])):
        registered=utc_time(cohort['registered_at_utc'])
        if not registered:raise ValueError('觀察組登錄時間不合法')
        start_local=registered.astimezone(TZ).date()
        for src in cohort['entries']:
            code=src['stock_id'];name=src.get('stock_name','');market=norm_market(src.get('market'))
            elig=src.get('forward_observation','')
            row={
                'cohort_id':cohort['cohort_id'],'stock_id':code,'stock_name':name,
                'market':market,'signal_price_asof':src.get('price_asof',''),
                'signal_first_observed_at_utc':cohort['first_signal_observed_at_utc'],
                'cohort_registered_at_utc':cohort['registered_at_utc'],
                'observation_status':elig,'audit_flags':src.get('audit_flags',''),
                'chip_strength_rank':src.get('chip_strength_rank',''),
                'chip_strength_score':src.get('chip_strength_score',''),
                'technical_confirmed_count':src.get('technical_confirmed_count',''),
                'technical_status':src.get('technical_status',''),
                'holder_structure':src.get('holder_structure',''),
                'reference_session':'','performance_status':'不計算_未核實還原OHLC及交易執行價格',
                'note':'僅顯示交易日觀察進度；非績效、交易訊號或買賣建議'
            }
            dates=[d for d in sessions[market] if d>start_local]
            market_problem=(cohort['cohort_id'],code) in market_conflicts
            if elig=='可前瞻觀察_仍需來源核實' and dates and not market_problem:
                row['reference_session']=dates[0].isoformat()
            for horizon in HORIZONS:
                h=f'h{horizon}'
                if elig=='不列入_非有效排名':
                    status='不列入_非有效排名';progress=0;target=''
                elif elig=='暫緩_資料須核對':
                    status='暫緩_異常待核實';progress=0;target=''
                elif elig!='可前瞻觀察_仍需來源核實':
                    raise ValueError('無效的前瞻觀察狀態')
                elif market_problem:
                    status='暫緩_市場別變更待核實';progress=0;target=''
                elif not dates:
                    status='等待參考交易日';progress=0;target=''
                else:
                    # First observed full session after cohort registration is the
                    # conservative reference day, NOT a simulated entry fill.
                    progress=min(max(len(dates)-1,0),horizon)
                    target=dates[horizon].isoformat() if len(dates)>horizon else ''
                    status='觀察期已走完_報酬尚未驗證' if target else '觀察中_無績效'
                row[h+'_observed_sessions']=progress
                row[h+'_target_session']=target
                row[h+'_status']=status
                counters[str(horizon)][status]+=1
            if elig!='可前瞻觀察_仍需來源核實' or market_problem:
                issues.append({'cohort_id':cohort['cohort_id'],'stock_id':code,
                               'stock_name':name,'issue_type':'市場別變更待確認' if market_problem else '資料品質隔離',
                               'description':('封存市場別與目前市場別不一致' if market_problem else (src.get('audit_flags') or elig))})
            records.append(row)
    return records,issues,{k:dict(v) for k,v in counters.items()}


def run(data_dir=DATA, observed_at=None, min_symbols=MIN_MARKET_SYMBOLS):
    data_dir=Path(data_dir)
    now=observed_at or dt.datetime.now(UTC)
    if now.tzinfo is None:raise ValueError('2.4C時間必須含時區')
    now=now.astimezone(UTC)
    index,latest,snap,first_ts,audit_rows,audit=valid_source(data_dir,now)
    registry, known=validate_cohort_registry(data_dir)
    fp=latest['signal_fingerprint']
    added=False
    if fp not in known:
        cohort=make_cohort(latest,snap,first_ts,audit_rows,audit,now,
                           digest((data_dir/'pit_audit.csv').read_bytes()))
        target=data_dir/'forward_cohorts'/(cohort['cohort_id']+'.json')
        if target.exists():raise FileExistsError('觀察組檔案已存在但不在索引，拒絕覆蓋')
        sha=write_json(target,cohort)
        registry['cohorts'].append({
            'cohort_id':cohort['cohort_id'],
            'cohort_path':target.relative_to(data_dir).as_posix(),
            'cohort_sha256':sha,
            'signal_fingerprint':fp,
            'registered_at_utc':cohort['registered_at_utc'],
            'first_signal_observed_at_utc':cohort['first_signal_observed_at_utc'],
            'qualified_entries':cohort['qualified_entries'],
            'source_snapshot_id':cohort['source_snapshot_id']})
        registry['cohorts_total']=len(registry['cohorts'])
        registry['version']=VERSION
        write_json(data_dir/'forward_cohorts_index.json',registry)
        known[fp]=cohort
        added=True
    # Re-check historical registry before emitting outputs. No old cohort mutation.
    registry,known=validate_cohort_registry(data_dir)
    cohort_list=list(known.values())
    sessions,sessions_count,market_conflicts=market_sessions(data_dir,cohort_list,now,min_symbols)
    rows,issues,status_counts=make_observations(cohort_list,sessions,market_conflicts)
    write_csv(data_dir/'forward_observation.csv',rows,CSV_COLS)
    write_csv(data_dir/'forward_data_issues.csv',issues,ISSUE_COLS)
    result={
        'version':VERSION,'status':'ok',
        'generated_at_taipei':now.astimezone(TZ).isoformat(timespec='seconds'),
        'latest_audited_snapshot_id':latest['snapshot_id'],
        'latest_signal_first_observed_at_utc':zulu(first_ts),
        'latest_cohort_id':known[fp]['cohort_id'],
        'new_cohort_created':added,
        'cohorts_total':len(cohort_list),
        'latest_cohort_registered_at_utc':known[fp]['registered_at_utc'],
        'latest_cohort_qualified':known[fp]['qualified_entries'],
        'observation_rows_all_cohorts':len(rows),
        'observation_eligible_rows_all_cohorts':sum(r['observation_status']=='可前瞻觀察_仍需來源核實' for r in rows),
        'data_quality_isolated_rows':len(issues),
        'market_classification_conflicts':len(market_conflicts),
        'unique_signal_fingerprints_in_archive':index.get('unique_signal_fingerprints'),
        'repeat_signal_snapshots':index.get('repeated_signal_snapshots'),
        'horizon_status_counts':status_counts,
        'session_coverage':{
            'method':'股票歷史CSV中按市場統計，每日有至少指定數量不重複股票且收盤價有效，即暫列觀察交易日；非官方交易日曆',
            'minimum_symbols_per_market_day':min_symbols,
            'usable_market_sessions':sessions_count,
            'coverage_dates':{market:{'first':dates[0].isoformat() if dates else None,'last':dates[-1].isoformat() if dates else None}
                              for market,dates in sessions.items()},
        },
        'horizon_definitions':{
            'reference_day':'首次2.4C觀察組登錄日之後第一個資料覆蓋充分的市場交易日（僅供計數）',
            '10':'參考日之後的第10個觀察交易日','20':'參考日之後的第20個觀察交易日',
            '60':'參考日之後的第60個觀察交易日',
        },
        'performance_metrics_enabled':False,
        'strict_historical_backtest_eligible':0,
        'performance_blockers':[
            'price_history.csv只包含未還原收盤價，缺官方核實的還原OHLC、公司行動及現金股利',
            '交易日曆暫從已取得行情的有效涵蓋度推估，未獨立核實交易所完整交易日曆',
            '未驗證當時可成交的委託時點、開盤參考價、流動性及交易成本',
            '訊號首次封存時間與官方正式公布時間不可混為一談',
            '同股跨交易日反覆出現的訊號可能重疊，不可視為獨立統計樣本',
        ],
        'outputs':['forward_observation_meta.json','forward_observation.csv',
                   'forward_data_issues.csv','forward_cohorts_index.json','forward_cohorts/'],
    }
    write_json(data_dir/'forward_observation_meta.json',result)
    print('2.4C observation tracker:', 'cohorts=',len(cohort_list),
          'new=',added,'eligible=',result['observation_eligible_rows_all_cohorts'],
          'NO PERFORMANCE RETURNS')
    return result,rows


if __name__=='__main__':
    p=argparse.ArgumentParser(description='TPE-MFDS 2.4C prospective observations (no return figures)')
    p.add_argument('--data-dir',type=Path,default=DATA)
    opts=p.parse_args()
    run(opts.data_dir)
