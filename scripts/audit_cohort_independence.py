#!/usr/bin/env python3
"""TPE-MFDS 2.4F: point-in-time cohort version / overlap research audit.

Read-only with respect to all archived forward cohorts, chip ranking, and returns.
A distinct SHA-256 fingerprint is NOT proof of a new independent market session.
Same-session revisions are preserved with timing caveats, never silently merged.
No performance metrics or statistical independence claims are made.
"""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site'/'data'
VERSION='2.4F'
UTC=dt.timezone.utc
OUT_COLUMNS=[
 'cohort_id','registered_at_utc','first_signal_observed_at_utc',
 'source_price_dates','holder_asof_dates','flow_asof_dates',
 'qualified_entries','candidate_entries','session_group_key',
 'revision_number_in_group','versions_in_session_group',
 'research_version_status','sample_independence_verified',
 'performance_sample_eligible','notes'
]
CHANGE_COLUMNS=[
 'session_group_key','earlier_cohort_id','later_cohort_id','stock_id',
 'earlier_holder_asof','later_holder_asof','earlier_chip_rank',
 'later_chip_rank','earlier_chip_score','later_chip_score',
 'earlier_forward_status','later_forward_status',
 'earlier_audit_flags','later_audit_flags',
 'rank_changed','score_changed','qualification_or_flag_changed'
]


def sha(raw:bytes)->str: return hashlib.sha256(raw).hexdigest()
def parse_datetime(s):
 try:
  d=dt.datetime.fromisoformat(str(s).replace('Z','+00:00'))
  return d.astimezone(UTC) if d.tzinfo is not None else None
 except (TypeError,ValueError,OverflowError): return None

def parse_date(s):
 try: return dt.date.fromisoformat(str(s))
 except (ValueError,TypeError): return None

def read_json(p):
 o=json.loads(p.read_text(encoding='utf-8-sig'))
 if not isinstance(o,dict):raise ValueError(f'JSON根節點不是物件: {p}')
 return o

def write_json(p,obj):
 p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def write_csv(p,rows,cols):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)


def load_frozen_cohorts(data_dir):
 index=read_json(data_dir/'forward_cohorts_index.json')
 records=index.get('cohorts',[])
 if index.get('version')!='2.4C' or not isinstance(records,list) or index.get('cohorts_total')!=len(records):
  raise ValueError('2.4C觀察組索引格式或筆數不一致')
 base=(data_dir/'forward_cohorts').resolve()
 result=[]; seen_id=set();seen_fp=set()
 for item in records:
  if not isinstance(item,dict):raise ValueError('觀察組索引內容不是物件')
  cohort_id=item.get('cohort_id')
  fingerprint=item.get('signal_fingerprint')
  if not isinstance(cohort_id,str) or not re.fullmatch(r'cohort-[0-9a-f]{24}',cohort_id):
   raise ValueError('觀察組編號不合法')
  if not isinstance(fingerprint,str) or not re.fullmatch(r'[a-f0-9]{64}',fingerprint):
   raise ValueError('訊號指紋不合法')
  if cohort_id in seen_id or fingerprint in seen_fp:raise ValueError('觀察組編號或訊號指紋重複')
  seen_id.add(cohort_id); seen_fp.add(fingerprint)
  loc=(data_dir/str(item.get('cohort_path',''))).resolve()
  if not loc.is_relative_to(base) or loc.name != cohort_id+'.json' or not loc.is_file():
   raise ValueError('觀察組封存路徑不合法或檔案不存在')
  raw=loc.read_bytes()
  if sha(raw)!=item.get('cohort_sha256'):raise ValueError(f'{cohort_id} SHA-256來源封存校驗失敗')
  cohort=json.loads(raw.decode('utf-8-sig'))
  if not isinstance(cohort,dict) or cohort.get('cohort_id')!=cohort_id or cohort.get('signal_fingerprint')!=fingerprint:
   raise ValueError('觀察組索引與封存欄位不一致')
  registered=parse_datetime(cohort.get('registered_at_utc'))
  observed=parse_datetime(cohort.get('first_signal_observed_at_utc'))
  if registered is None or observed is None or registered<observed:
   raise ValueError('觀察組建立與首次訊號時間不合法')
  entries=cohort.get('entries')
  if not isinstance(entries,list) or len(entries)==0:raise ValueError('觀察組候選股票為空')
  ids=[]; price_dates=set();holder_dates=set();flow_dates=set(); qualified=0
  byid={}
  for entry in entries:
   if not isinstance(entry,dict):raise ValueError('觀察組股票紀錄不是物件')
   sid=str(entry.get('stock_id',''))
   if not re.fullmatch(r'[0-9A-Za-z]{4,8}',sid) or sid in byid:raise ValueError('觀察組股票代碼重複或不合法')
   ids.append(sid);byid[sid]=entry
   price=entry.get('price_asof')
   if not parse_date(price): raise ValueError(f'{sid} price_asof 無效')
   price_dates.add(str(price))
   flow=str(entry.get('flow_asof','')).strip();holder=str(entry.get('holder_asof','')).strip()
   if flow and not parse_date(flow):raise ValueError(f'{sid} flow_asof 無效')
   if holder and not parse_date(holder):raise ValueError(f'{sid} holder_asof 無效')
   if flow:flow_dates.add(flow)
   if holder:holder_dates.add(holder)
   status=str(entry.get('forward_observation','')).strip()
   if status not in ('可前瞻觀察_仍需來源核實','暫緩_資料須核對','不列入_非有效排名'):
    raise ValueError(f'{sid} forward_observation 狀態無法識別')
   qualified+= status=='可前瞻觀察_仍需來源核實'
  if qualified!=cohort.get('qualified_entries'):
   raise ValueError(f'{cohort_id} 合格股票數與封存摘要不一致')
  declared=cohort.get('source_price_dates')
  if not isinstance(declared,list) or set(declared)!=price_dates:
   raise ValueError(f'{cohort_id} source_price_dates與逐檔行情日期不一致')
  result.append({'id':cohort_id,'fp':fingerprint,'registered':registered,
    'observed':observed,'raw':cohort,'byid':byid,
    'price_dates':tuple(sorted(price_dates)),'holder_dates':tuple(sorted(holder_dates)),
    'flow_dates':tuple(sorted(flow_dates)),'qualified':qualified,'candidate':len(entries)})
 # Fail rather than silently ignoring orphaned immutable files.
 if base.exists() and set(p.stem for p in base.glob('*.json')) != seen_id:
  raise ValueError('觀察組檔案與索引不一致，有未索引或遺失的封存')
 return result


def build_report(cohorts,now):
 groups=defaultdict(list)
 for c in cohorts:groups[c['price_dates']].append(c)
 rows=[];changes=[];group_info=[]
 for price_days,versions in sorted(groups.items()):
  versions=sorted(versions,key=lambda v:(v['registered'],v['id']))
  group_key='|'.join(price_days)
  n=len(versions)
  n_status_changes=0; n_rank_changes=0;n_score_changes=0; n_shared=0
  for seq,c in enumerate(versions,1):
   status=('同收盤日多版本_待確認資料公布時點' if n>1 else '單一收盤資料日期版本_仍未證明統計獨立')
   rows.append({
    'cohort_id':c['id'],'registered_at_utc':c['raw']['registered_at_utc'],
    'first_signal_observed_at_utc':c['raw']['first_signal_observed_at_utc'],
    'source_price_dates':group_key,'holder_asof_dates':'|'.join(c['holder_dates']),
    'flow_asof_dates':'|'.join(c['flow_dates']),
    'qualified_entries':c['qualified'],'candidate_entries':c['candidate'],
    'session_group_key':group_key,'revision_number_in_group':seq,
    'versions_in_session_group':n,'research_version_status':status,
    'sample_independence_verified':False,'performance_sample_eligible':False,
    'notes':'保存原始封存；同交易日更新屬資料版本，不可憑指紋不同重複當作獨立績效樣本'
   })
  for earlier,later in zip(versions,versions[1:]):
   shared=sorted(set(earlier['byid'])&set(later['byid']))
   n_shared+=len(shared)
   for sid in shared:
    a,b=earlier['byid'][sid],later['byid'][sid]
    changed_rank=str(a.get('chip_strength_rank',''))!=str(b.get('chip_strength_rank',''))
    changed_score=str(a.get('chip_strength_score',''))!=str(b.get('chip_strength_score',''))
    changed_status=(a.get('forward_observation')!=b.get('forward_observation') or
                    a.get('audit_flags','')!=b.get('audit_flags',''))
    n_rank_changes+=changed_rank;n_score_changes+=changed_score;n_status_changes+=changed_status
    if changed_rank or changed_score or changed_status or a.get('holder_asof')!=b.get('holder_asof'):
     changes.append({
      'session_group_key':group_key,'earlier_cohort_id':earlier['id'],
      'later_cohort_id':later['id'],'stock_id':sid,
      'earlier_holder_asof':a.get('holder_asof',''), 'later_holder_asof':b.get('holder_asof',''),
      'earlier_chip_rank':a.get('chip_strength_rank',''), 'later_chip_rank':b.get('chip_strength_rank',''),
      'earlier_chip_score':a.get('chip_strength_score',''), 'later_chip_score':b.get('chip_strength_score',''),
      'earlier_forward_status':a.get('forward_observation',''),
      'later_forward_status':b.get('forward_observation',''),
      'earlier_audit_flags':a.get('audit_flags',''), 'later_audit_flags':b.get('audit_flags',''),
      'rank_changed':changed_rank,'score_changed':changed_score,
      'qualification_or_flag_changed':changed_status})
  group_info.append({
   'source_price_dates':list(price_days), 'group_key':group_key,
   'cohort_versions':n, 'cohort_ids':[x['id'] for x in versions],
   'qualified_entry_counts':[x['qualified'] for x in versions],
   'holder_dates_by_version':[list(x['holder_dates']) for x in versions],
   'shared_symbol_pairs_adjacent':n_shared,
   'rank_changes_adjacent':n_rank_changes,
   'score_changes_adjacent':n_score_changes,
   'qualification_or_flag_changes_adjacent':n_status_changes,
   'status': 'multiple_versions_same_price_session_cannot_count_independently' if n>1 else 'single_version_timing_and_overlap_still_unverified'
  })
 report={
  'version':VERSION,'status':'ok_guardrails_active','generated_at_taipei':now.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec='seconds'),
  'archived_cohorts_total':len(cohorts),'price_session_groups_total':len(groups),
  'multi_version_price_session_groups':sum(len(x)>1 for x in groups.values()),
  'cohorts_in_multi_version_groups':sum(len(x) for x in groups.values() if len(x)>1),
  'total_candidate_entries_all_versions':sum(c['candidate'] for c in cohorts),
  'total_qualified_entries_all_versions':sum(c['qualified'] for c in cohorts),
  'revision_change_rows':len(changes),
  'performance_metrics_enabled':False,'sample_independence_verified':False,
  'strict_performance_samples_eligible':0,
  'source_publication_times_verified':False,
  'meaning':'相同收盤交易日的不同訊號指紋屬不同資料版本；其建立時間可能不同，不能直接視為獨立績效樣本，也不能任意選最新版本倒填交易決策時間。',
  'market_session_notice':'臨時停市與上櫃獨立交易日仍須以可靠來源個別核實；本稽核不取代2.4D交易日曆。',
  'outputs':['cohort_independence_meta.json','cohort_independence.csv','cohort_revision_changes.csv'],
  'groups':group_info
 }
 return report,rows,changes


def run(data_dir=DATA,now=None):
 now=now or dt.datetime.now(UTC)
 cohorts=load_frozen_cohorts(data_dir)
 report,rows,changes=build_report(cohorts,now)
 write_json(data_dir/'cohort_independence_meta.json',report)
 write_csv(data_dir/'cohort_independence.csv',rows,OUT_COLUMNS)
 write_csv(data_dir/'cohort_revision_changes.csv',changes,CHANGE_COLUMNS)
 print('2.4F completed:', report['archived_cohorts_total'],'versions /',report['price_session_groups_total'],'price-date groups /',report['multi_version_price_session_groups'],'multi-version groups /',len(changes),'change rows; performance disabled')
 return report

if __name__=='__main__':run()
