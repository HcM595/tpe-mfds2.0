#!/usr/bin/env python3
"""TPE-MFDS 2.4B — non-predictive, source-aware point-in-time research audit.

The previous 2.4A snapshot is the **earliest defensible system-observed time**
for these signals.  Neither the market data date nor the weekly TDCC balance
reference date proves a public publication timestamp. This script NEVER
retroactively declares historical signals tradable, NEVER overwrites 2.4A
archives, and NEVER creates return metrics.

Run AFTER scripts/archive_signals.py and BEFORE the existing git commit.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'site' / 'data'
HISTORY = ROOT / 'history_data'
VERSION = '2.4B'
UTC = dt.timezone.utc
TZ = ZoneInfo('Asia/Taipei')
COLS = [
    'stock_id','stock_name','market','rank_status','chip_strength_rank',
    'chip_strength_score','technical_status','technical_confirmed_count',
    'holder_structure','price_asof','flow_asof','holder_asof',
    'signal_first_observed_at_utc','source_published_at_utc',
    'five_day_flow_audit','four_week_holder_audit','holder_historical_source',
    'holder_anomaly_flag','audit_flags','forward_observation','strict_historical_backtest',
    'earliest_entry_rule'
]


def iso_date(value):
    try: return dt.date.fromisoformat(str(value).strip())
    except (TypeError, ValueError): return None


def iso_datetime(value):
    try:
        value = str(value).strip()
        result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.astimezone(UTC) if result.tzinfo else None
    except (ValueError, TypeError): return None


def finite(value):
    try:
        f = float(str(value).strip().replace(',', ''))
        return f if math.isfinite(f) else None
    except (ValueError, TypeError): return None


def sha256(raw): return hashlib.sha256(raw).hexdigest()


def load_json(path):
    obj = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(obj, dict): raise ValueError('JSON不是物件: ' + str(path))
    return obj


def load_csv(path):
    if not path.exists(): return None
    with path.open(encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames: raise ValueError('CSV沒有欄位: '+str(path))
        return list(reader)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)


def validate_snapshot(data_dir):
    """Verify 2.4A indexed SHA, full archived source bytes, and first observation.

    Archive listing MUST come from the 2.4A index. File paths are constrained to
    the expected archive directory (never treat index paths as arbitrary paths).
    """
    index = load_json(data_dir/'signal_archive_index.json')
    entries = index.get('snapshots')
    if not isinstance(entries, list) or not entries:
        raise ValueError('缺少2.4A歷史快照，停止2.4B稽核')
    if index.get('snapshots_total') != len(entries):
        raise ValueError('2.4A索引數量不符')
    archive_dir = (data_dir/'signal_archive').resolve()
    ids, fingerprints = set(), {}
    for entry in entries:
        path = (data_dir / str(entry.get('snapshot_path',''))).resolve()
        if not path.is_relative_to(archive_dir) or path.name != 'snapshot.json':
            raise ValueError('索引含非法快照路徑')
        if entry.get('snapshot_id') in ids or not path.is_file():
            raise ValueError('歷史快照不存在或編號重複：'+str(path))
        ids.add(entry['snapshot_id'])
        raw = path.read_bytes()
        if sha256(raw) != entry.get('snapshot_sha256'):
            raise ValueError('快照SHA-256驗證失敗: '+str(path))
        snap = json.loads(raw)
        if snap.get('snapshot_id') != entry['snapshot_id'] or snap.get('archive_format') != 1:
            raise ValueError('快照身分或格式異常')
        if snap.get('signal_fingerprint') != entry.get('signal_fingerprint'):
            raise ValueError('快照訊號指紋不一致')
        timestamp = iso_datetime(snap.get('captured_at_utc'))
        if not timestamp or timestamp != iso_datetime(entry.get('captured_at_utc')):
            raise ValueError('快照封存時間異常')
        sig = entry['signal_fingerprint']
        previous = fingerprints.get(sig)
        if previous is None or timestamp < previous[0]:
            fingerprints[sig] = (timestamp, entry['snapshot_id'])
    # Newest *captured* snapshot, not by name or source date.
    latest = max(entries, key=lambda v:(iso_datetime(v['captured_at_utc']),v['snapshot_id']))
    latest_path = (data_dir / latest['snapshot_path']).resolve()
    snap = json.loads(latest_path.read_bytes())
    digest_map = snap.get('source_sha256') or {}
    for name, expected in digest_map.items():
        if '/' in name or '\\' in name or name.startswith('.'):
            raise ValueError('不安全的來源檔名')
        stored = latest_path.parent/'inputs'/(name+'.gz' if name.endswith('.csv') else name)
        if not stored.is_file(): raise FileNotFoundError('已封存來源遺失: '+str(stored))
        raw = gzip.decompress(stored.read_bytes()) if name.endswith('.csv') else stored.read_bytes()
        if sha256(raw) != expected:
            raise ValueError('已封存來源雜湊不符: '+name)
    required = {'chip_rank.csv','tech_crosscheck.csv','official_meta.json','chip_signals.csv'}
    if not required.issubset(digest_map):
        raise ValueError('快照缺必要來源')
    first_ts, first_id = fingerprints[latest['signal_fingerprint']]
    reported_first = latest.get('first_seen_snapshot_id')
    if reported_first != first_id:
        raise ValueError('同訊號首次觀測快照指向異常')
    if snap.get('source_published_at') not in (None,''):
        # Do not trust arbitrary publication time until a dedicated, independently
        # verified source-release-time registry is implemented.
        raise ValueError('封存已填寫未驗證的source_published_at，需人工檢視')
    return index, latest, snap, latest_path, first_ts, first_id


def rows_by_code(rows, label):
    out={}
    for row in rows or []:
        code = str(row.get('stock_id','')).strip()
        if not code or code in out: raise ValueError(label+'股票代號重複或空白')
        out[code]=row
    return out


def flow_check(history, code, asof, foreign_expected, trust_expected):
    if history is None: return '缺歷史資料_待核對'
    asof_d = iso_date(asof)
    if not asof_d: return '日期異常'
    rows = []
    dates = set()
    for r in history:
        if r.get('stock_id','').strip()!=code: continue
        d = iso_date(r.get('date'))
        if d and d <= asof_d:
            rows.append((d,r))
    rows.sort(key=lambda t:t[0])
    last = rows[-5:]
    if len(last)!=5 or len({d for d,_ in last})!=5 or last[-1][0]!=asof_d:
        return '法人歷史未滿五筆或日期不符'
    if (last[-1][0]-last[0][0]).days > 14:
        return '法人五日間距過長'
    values = [(finite(r.get('foreign_net_shares')),finite(r.get('trust_net_shares'))) for _,r in last]
    if any(a is None or b is None for a,b in values):return '法人原始值缺漏'
    expect = (finite(foreign_expected),finite(trust_expected))
    if expect[0] is None or expect[1] is None:return '籌碼五日總和缺漏'
    if abs(sum(a for a,b in values)-expect[0])>1 or abs(sum(b for a,b in values)-expect[1])>1:
        return '五日累計與原始資料不一致'
    return '五日算術核對一致'


def holder_check(history, code, asof, delta400, delta1000):
    """Check weekly deltas from current history (NOT proof of historical availability)."""
    if history is None:return '缺歷史資料_待核對','未知'
    d = iso_date(asof)
    if not d:return '日期異常','未知'
    rows = []
    for r in history:
        if r.get('stock_id','').strip()!=code:continue
        day=iso_date(r.get('date'))
        if day and day<=d:rows.append((day,r))
    rows.sort(key=lambda t:t[0]); unique={day:rr for day,rr in rows}
    cur = unique.get(d)
    if cur is None:return '缺當週集保紀錄','未知'
    candidates=[(k,v) for k,v in unique.items() if 24 <= (d-k).days <= 35]
    if not candidates:return '缺四週前可比較週次',str(cur.get('source','未知'))[:100]
    prior=min(candidates,key=lambda pair:abs((d-pair[0]).days-28))[1]
    a,b = finite(cur.get('holder400_pct')),finite(prior.get('holder400_pct'))
    c,e = finite(cur.get('holder1000_pct')),finite(prior.get('holder1000_pct'))
    da,dc = finite(delta400),finite(delta1000)
    sources = sorted({str(cur.get('source','未知')).strip(),str(prior.get('source','未知')).strip()})
    source = ' + '.join(sources)[:160]
    if None in (a,b,c,e,da,dc):return '持股資料缺值',source
    if abs((a-b)-da)>0.11 or abs((c-e)-dc)>0.11:
        return '四週持股差異與歷史資料不一致',source
    if not(0<=c<=a<=101 and 0<=e<=b<=101):return '持股比例級距異常',source
    return '四週算術核對一致_公布時間未確認',source


def audit(data_dir=DATA, history_dir=HISTORY):
    data_dir,history_dir=Path(data_dir),Path(history_dir)
    index,latest,snap,snap_path,first_ts,first_id=validate_snapshot(data_dir)
    # Audit frozen snapshot signals, not today's mutable CSVs.
    archived=snap.get('signals')
    if not isinstance(archived,list) or not archived:raise ValueError('快照缺少逐檔訊號')
    archive_by_code=rows_by_code(archived,'快照訊號')
    # Use only the archived source bytes for date and score identity checks.
    def archived_csv(name):
        raw=gzip.decompress((snap_path.parent/'inputs'/(name+'.gz')).read_bytes())
        return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    rank=rows_by_code(archived_csv('chip_rank.csv'),'原始排名')
    tech=rows_by_code(archived_csv('tech_crosscheck.csv'),'原始技術')
    if set(rank)!=set(tech) or set(rank)!=set(archive_by_code):
        raise ValueError('快照逐檔訊號與原始資料股票池不一致')
    if len(rank)!=snap.get('summary',{}).get('rank_candidates'):
        raise ValueError('快照候選筆數與明細不一致')
    flow=load_csv(history_dir/'institutional_daily.csv')
    holder=load_csv(history_dir/'holder_weekly.csv')
    prices=load_csv(data_dir/'price_history.csv')
    price_day_map={}
    if prices is not None:
        for r in prices:
            code=r.get('stock_id','').strip()
            d=iso_date(r.get('date'))
            if code and d:
                current=price_day_map.get(code)
                if current is None or d>current:price_day_map[code]=d
    details=[];anomalies=[];flow_counts=Counter();holder_counts=Counter();status_counts=Counter()
    for code,r in sorted(rank.items()):
        t=tech[code]; frozen=archive_by_code[code]
        if any(str(r.get(field,'')).strip()!=str(frozen.get(field,'')).strip()
               for field in ('price_asof','flow_asof','holder_asof','chip_strength_score','chip_strength_rank','rank_status')):
            raise ValueError(f'{code} 快照內容與來源排名不一致')
        if str(t.get('data_status','')).strip()!=str(frozen.get('technical_data_status','')).strip():
            raise ValueError(f'{code} 技術狀態與快照不符')
        flags=[]
        ranked=r.get('rank_status')=='可排名'
        date=iso_date(r.get('price_asof')); flow_date=iso_date(r.get('flow_asof'))
        holder_date=iso_date(r.get('holder_asof'))
        if not date or (ranked and (date!=flow_date or holder_date is None or holder_date>date)):
            flags.append('資料日期不一致或缺漏')
        if date and first_ts.astimezone(TZ).date()<date:
            flags.append('交易日晚於首次封存日')
        if ranked and t.get('data_status')!='可驗證':flags.append('技術資料未通過')
        c400=finite(r.get('large400_4w_pp')); c1000=finite(r.get('large1000_4w_pp'))
        if ranked and (c400 is None or c1000 is None):flags.append('大戶四週數值缺漏')
        fcheck=flow_check(flow,code,r.get('flow_asof'),r.get('foreign_5d_shares'),r.get('trust_5d_shares')) if ranked else '未排名_不核對'
        hcheck,hsource=holder_check(holder,code,r.get('holder_asof'),r.get('large400_4w_pp'),r.get('large1000_4w_pp')) if ranked else ('未排名_不核對','未排名')
        if fcheck in ('法人歷史未滿五筆或日期不符','法人五日間距過長','法人原始值缺漏','籌碼五日總和缺漏','五日累計與原始資料不一致','日期異常'):
            flags.append('法人算術或來源資料異常')
        if hcheck in ('缺當週集保紀錄','缺四週前可比較週次','持股資料缺值','四週持股差異與歷史資料不一致','持股比例級距異常','日期異常'):
            flags.append('集保持股原始紀錄異常或缺漏')
        # The original 2.3.3 anomaly list is authoritative for this version;
        # also fail closed on any new gross four-week movement.
        anom=(bool(str(t.get('holder_anomaly') or '').strip()) or
              (c400 is not None and abs(c400)>=10) or
              (c1000 is not None and abs(c1000)>=10))
        if anom:flags.append('大戶持股大幅變動_需人工核實')
        if ranked and price_day_map and price_day_map.get(code) is not None and price_day_map[code]<date:
            flags.append('目前價格歷史缺當日紀錄')
        if not ranked:forward='不列入_非有效排名'
        elif flags:forward='暫緩_資料須核對'
        else:forward='可前瞻觀察_仍需來源核實'
        # Strict historical and execution backtest needs verified publication,
        # historical security master, adjusted OHLC, an executable entry clock.
        strict='不可使用_公布時點及公司行動尚未驗證'
        rec={
            'stock_id':code,'stock_name':r.get('stock_name',''),'market':r.get('market',''),
            'rank_status':r.get('rank_status',''),'chip_strength_rank':r.get('chip_strength_rank',''),
            'chip_strength_score':r.get('chip_strength_score',''),
            'technical_status':t.get('technical_status',''),
            'technical_confirmed_count':t.get('technical_confirmed_count',''),
            'holder_structure':t.get('holder_structure',''),
            'price_asof':r.get('price_asof',''),'flow_asof':r.get('flow_asof',''),
            'holder_asof':r.get('holder_asof',''),
            'signal_first_observed_at_utc':first_ts.isoformat().replace('+00:00','Z'),
            'source_published_at_utc':'',
            'five_day_flow_audit':fcheck,
            'four_week_holder_audit':hcheck,
            'holder_historical_source':hsource,
            'holder_anomaly_flag':'是' if anom else '否',
            'audit_flags':'；'.join(flags),
            'forward_observation':forward,
            'strict_historical_backtest':strict,
            'earliest_entry_rule':'首次實際封存之後的可交易時段；開盤日期與價格須在2.4C另行確定'
        }
        details.append(rec)
        status_counts[forward]+=1
        flow_counts[fcheck]+=1
        holder_counts[hcheck]+=1
        if anom:
            anomalies.append({key:rec[key] for key in (
                'stock_id','stock_name','chip_strength_rank','price_asof',
                'holder_asof','four_week_holder_audit','holder_historical_source',
                'holder_anomaly_flag','audit_flags','forward_observation')})
    expected_rank=snap['summary']['eligible_ranked']
    if sum(r.get('rank_status')=='可排名' for r in rank.values())!=expected_rank:
        raise ValueError('已封存有效排名數量不一致')
    if len(tech)!=snap['summary']['rank_candidates']:
        raise ValueError('已封存技術樣本數量不一致')
    summary={
        'version':VERSION, 'status':'ok',
        'note_status':'ok表示稽核成功產出，不代表通過嚴格回測',
        'generated_at_taipei':dt.datetime.now(TZ).isoformat(timespec='seconds'),
        'audited_snapshot_id':latest['snapshot_id'],
        'first_seen_snapshot_id':first_id,
        'signal_first_observed_at_utc':first_ts.isoformat().replace('+00:00','Z'),
        'audited_source_dates':snap['summary'].get('source_price_dates',[]),
        'snapshot_index_total':index['snapshots_total'],
        'unique_signal_fingerprints':index['unique_signal_fingerprints'],
        'repeated_signal_snapshots':index['repeated_signal_snapshots'],
        'snapshot_integrity':'indexed_sha256_and_archived_source_hashes_verified',
        'candidate_rows':len(details), 'eligible_ranked':expected_rank,
        'forward_observation_status_counts':dict(status_counts),
        'strict_historical_backtest_eligible':0,
        'manual_holder_anomaly_count':len(anomalies),
        'manual_holder_anomalies':[{'stock_id':r['stock_id'],'stock_name':r['stock_name']} for r in anomalies],
        'flow_arithmetic_status_counts':dict(flow_counts),
        'holder_arithmetic_status_counts':dict(holder_counts),
        'source_time_metadata':{
            'official_price_day':'日期已知，官方精確發布時間未逐日核對',
            'institutional_flow':'交易日已知，官方精確發布時間未逐筆核對',
            'tdcc_weekly':'持股基準週已知，實際公布時間未知；部分歷史來自非官方鏡像',
            'signal_first_observation':'封存快照首次出現的UTC時間，並非來源正式公告時間',
            'price_corporate_actions':'未驗證還原價格與除權息調整',
            'historic_security_master':'未重建歷史各時點上市櫃普通股名錄',
        },
        'unverified_data_availability':[
            '不可將資料交易日或集保持股週次直接當作來源公告時間',
            '不可將系統第一次封存時間倒填至更早日期',
            '不可使用當前股東週資料補算封存日前歷史選股訊號',
            '可前瞻觀察不等於可執行報酬回測；需等2.4C取得進出場日期與還原OHLC',
            '歷史檔案算術核對僅是事後品質查核，不證明當時已發布',
        ],
        'artifact_files':['pit_audit.csv','pit_anomalies.csv','pit_audit_meta.json'],
    }
    write_csv(data_dir/'pit_audit.csv', details, COLS)
    anomaly_cols=['stock_id','stock_name','chip_strength_rank','price_asof',
                  'holder_asof','four_week_holder_audit','holder_historical_source',
                  'holder_anomaly_flag','audit_flags','forward_observation']
    write_csv(data_dir/'pit_anomalies.csv',anomalies,anomaly_cols)
    write_json(data_dir/'pit_audit_meta.json',summary)
    print('2.4B audit:',len(details),'candidates,',expected_rank,'ranked,',
          len(anomalies),'holder anomalies; strict historical backtest eligibility = 0')
    return summary,details


if __name__=='__main__':
    ap=argparse.ArgumentParser(description='TPE-MFDS 2.4B point-in-time and historical quality audit')
    ap.add_argument('--data-dir',type=Path,default=DATA)
    ap.add_argument('--history-dir',type=Path,default=HISTORY)
    args=ap.parse_args()
    audit(args.data_dir,args.history_dir)
