#!/usr/bin/env python3
"""TPE-MFDS 2.5A: cross-check archival research readiness and market exceptions.

Read-only w.r.t. pre-existing reports and immutable snapshot files. Never
calculate prices/returns, never infer a corporate-action-free history from a
rolling notice feed, and never turn secondary closure reports into official
calendar data. Conflicting/missing inputs fail closed in research readiness.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import datetime as dt
import json
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'site' / 'data'
VERSION = '2.5A'
UTC = dt.timezone.utc
TZ = ZoneInfo('Asia/Taipei')
COHORT_COLS = ['cohort_id', 'price_session', 'registered_at_utc', 'qualified_entries',
               'signal_version_group', 'original_cohort_preserved',
               'publication_timing_verified', 'independent_performance_sample',
               'return_calculation_allowed', 'reason']
ACTION_COLS = ['cohort_id', 'stock_id', 'stock_name', 'market', 'observation_status',
               'rolling_notice_observed', 'historical_corporate_actions_complete',
               'verified_adjusted_ohlc', 'return_calculation_allowed', 'reason']
EXCEPTION_COLS = ['market', 'date', 'issue', 'reference_source_type', 'reference_url',
                  'official_calendar_contains_date', 'market_daily_quote_on_date',
                  'official_temporary_closure_notice_archived', 'validation_state', 'effect_on_performance']
# This is a RESEARCH EXCEPTION record, NOT an official holiday feed update.
# Statements reported by CNA on Oct 22 and absence of TWSE daily turnover are
# supporting context only. Do not auto-modify the trading calendar.
EXCEPTIONS = [
    {'market': market, 'date': '2026-10-23', 'issue': '颱風臨時休市待補官方原始公告',
     'reference_source_type': '媒體轉述證交所與櫃買中心公告；非官方原始封存',
     'reference_url': 'https://www.cna.com.tw/news/afe/202610220388.aspx'}
    for market in ('上市', '上櫃')
]


def read_json(path):
    obj = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(obj, dict):
        raise ValueError(f'{path.name}: JSON root must be object')
    return obj


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as fh:
        rd = csv.DictReader(fh)
        if not rd.fieldnames: raise ValueError(f'{path.name}: CSV header missing')
        return list(rd)


def dump_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def dump_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as fh:
        wr = csv.DictWriter(fh, fieldnames=columns, extrasaction='ignore')
        wr.writeheader(); wr.writerows(rows)


def as_int(value, field):
    try:
        out = int(value)
    except (ValueError, TypeError):
        raise ValueError(f'{field}: expected integer')
    if out < 0: raise ValueError(f'{field}: negative count')
    return out


def date_ok(value):
    try:
        d = dt.date.fromisoformat(str(value))
        return d.isoformat() == str(value)
    except (ValueError, TypeError):
        return False


def iso_ok(value):
    try:
        d = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return d.tzinfo is not None
    except (ValueError, TypeError):
        return False


def evaluate(data_dir=DATA, now=None):
    data_dir = Path(data_dir)
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None: raise ValueError('run time must be timezone-aware')
    issues = []
    inputs = {}
    paths = {
        'cohorts_index': 'forward_cohorts_index.json',
        'cohort_independence': 'cohort_independence_meta.json',
        'forward_meta': 'forward_observation_meta.json',
        'corporate_meta': 'corporate_actions_meta.json',
        'official_calendar': 'official_session_calendar.json',
    }
    for key, filename in paths.items():
        try: inputs[key] = read_json(data_dir / filename)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as ex:
            issues.append(f'{filename}: {type(ex).__name__}: {str(ex)[:110]}')
    observation_rows = []
    try: observation_rows = read_csv(data_dir/'forward_observation.csv')
    except (OSError, ValueError, TypeError) as ex:
        issues.append('forward_observation.csv: '+type(ex).__name__)
    calendar = inputs.get('official_calendar', {})
    cal_years = calendar.get('years', {})
    if not isinstance(cal_years, dict): cal_years = {}; issues.append('invalid calendar years')
    cal_2026 = cal_years.get('2026', {})
    closed_dates = set(cal_2026.get('closed_dates', [])) if isinstance(cal_2026, dict) else set()
    if calendar.get('status') != 'ok': issues.append('TWSE official calendar not currently verified')
    for value in closed_dates:
        if not date_ok(value): issues.append('calendar contains malformed closed date'); break

    cohort_index = inputs.get('cohorts_index', {})
    items = cohort_index.get('cohorts', [])
    if not isinstance(items, list): issues.append('cohort index not list'); items = []
    if len(items) != len({x.get('cohort_id') for x in items if isinstance(x, dict)}):
        issues.append('duplicate cohort id')
    if as_int(cohort_index.get('cohorts_total', len(items)), 'cohorts_total') != len(items):
        issues.append('cohort index count mismatch')

    version_meta = inputs.get('cohort_independence', {})
    if version_meta and version_meta.get('status') != 'ok_guardrails_active':
        issues.append('2.4F independence guardrails inactive')
    if version_meta and version_meta.get('sample_independence_verified') is not False:
        issues.append('unexpected independence verification status')
    if version_meta and version_meta.get('strict_performance_samples_eligible') != 0:
        issues.append('unexpected strict performance eligible count')

    forward_meta = inputs.get('forward_meta', {})
    action_meta = inputs.get('corporate_meta', {})
    if forward_meta and forward_meta.get('performance_metrics_enabled') is not False:
        issues.append('2.4C performance prohibition missing')
    if action_meta and action_meta.get('status') != 'ok':
        issues.append('2.4E official rolling source status is not fully ok')
    if action_meta and action_meta.get('total_return_calculation_allowed') is not False:
        issues.append('2.4E total return prohibition missing')
    if action_meta and action_meta.get('historical_corporate_actions_complete') is not False:
        issues.append('2.4E historic corporate-action completeness guard missing')
    if action_meta and action_meta.get('adjusted_ohlc_verified') is not False:
        issues.append('2.4E adjusted OHLC protection missing')

    cohort_rows=[]
    eligible_sum=0
    for item in items:
        if not isinstance(item, dict): issues.append('invalid cohort index item'); continue
        ident=str(item.get('cohort_id',''))
        sourcefile=data_dir/str(item.get('cohort_path',''))
        # Only allow cohort archives underneath the expected immutable directory.
        try:
            if not sourcefile.resolve().is_relative_to((data_dir/'forward_cohorts').resolve()):
                raise ValueError('unsafe archive path')
            archive_bytes=sourcefile.read_bytes()
            if hashlib.sha256(archive_bytes).hexdigest() != item.get('cohort_sha256'):
                raise ValueError('archived cohort SHA256 does not match index')
            source = read_json(sourcefile)
            if source.get('cohort_id') != ident: raise ValueError('cohort id mismatch')
            if source.get('signal_fingerprint') != item.get('signal_fingerprint'):
                raise ValueError('signal fingerprint mismatch')
            registered = str(source.get('registered_at_utc', ''))
            dates = source.get('source_price_dates', [])
            if not iso_ok(registered) or not isinstance(dates,list) or len(dates)!=1 or not date_ok(dates[0]):
                raise ValueError('ambiguous source price session or registration time')
            if registered != item.get('registered_at_utc'): raise ValueError('registration timestamp mismatch')
            qualified=as_int(source.get('qualified_entries'), 'qualified_entries')
            if qualified!=as_int(item.get('qualified_entries'), 'index qualified_entries'):
                raise ValueError('qualified entry count differs from index')
            eligible_sum+=qualified
            group = dates[0]
            cohort_rows.append({'cohort_id': ident, 'price_session':group,
                'registered_at_utc':registered, 'qualified_entries':qualified,
                'signal_version_group':group, 'original_cohort_preserved':'是',
                'publication_timing_verified':'否', 'independent_performance_sample':'否',
                'return_calculation_allowed':'否',
                'reason':'同收盤日多版本與跨日重疊未能證明獨立；公告時間、還原價格仍未驗證'})
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as ex:
            issues.append(f'cohort {ident}: {type(ex).__name__}: {str(ex)[:90]}')
            cohort_rows.append({'cohort_id':ident, 'price_session':'', 'registered_at_utc':'',
                'qualified_entries':'', 'signal_version_group':'', 'original_cohort_preserved':'未確認',
                'publication_timing_verified':'否', 'independent_performance_sample':'否',
                'return_calculation_allowed':'否', 'reason':'觀察組檔案無法驗證'})
    counts=Counter(row['price_session'] for row in cohort_rows if row['price_session'])
    if version_meta and as_int(version_meta.get('archived_cohorts_total',0), '2.4F cohorts') != len(items):
        issues.append('2.4F and index cohort counts disagree')
    if version_meta and as_int(version_meta.get('total_qualified_entries_all_versions',0),'2.4F qualified') != eligible_sum:
        issues.append('2.4F and index qualified counts disagree')
    if version_meta and as_int(version_meta.get('price_session_groups_total',0),'2.4F date groups') != len(counts):
        issues.append('2.4F date group counts disagree')
    identities=[(str(r.get('cohort_id','')).strip(),str(r.get('stock_id','')).strip()) for r in observation_rows]
    if len(identities)!=len(set(identities)):
        issues.append('duplicate stock in same cohort')
    known_ids={str(x.get('cohort_id','')) for x in items if isinstance(x,dict)}
    if any(cid not in known_ids for cid,sid in identities):
        issues.append('forward observation refers to unknown cohort')
    if version_meta and as_int(version_meta.get('total_candidate_entries_all_versions',0),'2.4F candidate rows') != len(observation_rows):
        issues.append('2.4F candidate totals differ from forward observations')
    if forward_meta and as_int(forward_meta.get('observation_rows_all_cohorts',0),'2.4C rows') != len(observation_rows):
        issues.append('forward CSV and 2.4C meta counts disagree')
    if action_meta and as_int(action_meta.get('forward_observation_rows',0),'2.4E rows') != len(observation_rows):
        issues.append('2.4E coverage cohort count differs from forward CSV')

    # Read 2.4E output as a current ROLLING notice only; never treat absence as no event.
    observed=set()
    try:
        action_rows=read_csv(data_dir/'corporate_actions_observed.csv')
        for row in action_rows:
            market=str(row.get('market','')).strip()
            stock=str(row.get('stock_id','')).strip()
            if market and stock: observed.add((market,stock))
    except (OSError,ValueError,TypeError) as ex:
        issues.append('corporate_actions_observed.csv: '+type(ex).__name__)
    action_audit=[]
    for row in observation_rows:
        cid=str(row.get('cohort_id','')).strip()
        sid=str(row.get('stock_id','')).strip()
        market=str(row.get('market','')).strip()
        if not (cid and sid and market):
            issues.append('forward row missing cohort/stock/market identity')
        action_audit.append({
            'cohort_id':cid, 'stock_id':sid, 'stock_name':str(row.get('stock_name','')).strip(),
            'market':market,
            'observation_status':str(row.get('forward_observation',row.get('observation_status',''))),
            'rolling_notice_observed': '是' if (('TWSE' if market=='上市' else 'TPEx'),sid) in observed else '否',
            'historical_corporate_actions_complete':'否',
            'verified_adjusted_ohlc':'否',
            'return_calculation_allowed':'否',
            'reason':'僅有滾動公告，無法認定歷史完整；不得算報酬'} )
    # Exceptional closure is NEVER silently added to the official calendar.
    exceptions=[]
    for item in EXCEPTIONS:
        exceptions.append({**item,
            'official_calendar_contains_date': '是' if item['date'] in closed_dates else '否',
            'market_daily_quote_on_date':'未獨立驗證',
            'official_temporary_closure_notice_archived':'否',
            'validation_state':'臨時休市有可信報導，官方原始公告尚未封存',
            'effect_on_performance':'只提示人工核實；不更改官方行事曆、不加入績效樣本'})
    if not items: issues.append('no historic cohorts')
    if not observation_rows: issues.append('no forward observations')
    if not action_meta: issues.append('no corporate action metadata')
    if not version_meta: issues.append('no cohort independence metadata')

    out={'version':VERSION, 'status':'ok_guardrails_active' if not issues else 'data_gap_fail_closed',
         'generated_at_taipei':now.astimezone(TZ).isoformat(timespec='seconds'),
         'purpose':'稽核資料可追溯性與缺口；不是驗證報酬、不是完整公司行動回補',
         'cohorts_in_index':len(items), 'cohorts_verified':sum(r['original_cohort_preserved']=='是' for r in cohort_rows),
         'price_session_groups':len(counts), 'groups_with_multiple_versions':sum(v>1 for v in counts.values()),
         'qualified_entries_index_sum':eligible_sum, 'forward_observation_rows':len(observation_rows),
         'rolling_notice_stock_market_pairs_observed':len(observed),
         'observation_rows_with_rolling_notice':sum(x['rolling_notice_observed']=='是' for x in action_audit),
         'extraordinary_market_closure_leads':len(exceptions),
         'official_temporary_closures_archived':0,
         'historical_corporate_actions_complete':False,'adjusted_ohlc_verified':False,
         'source_publication_times_verified':False, 'sample_independence_verified':False,
         'performance_metrics_enabled':False,'strict_performance_samples_eligible':0,
         'blocking_issues':issues,
         'notes':['沒有近期滾動除權息公告，不代表歷史上沒有公司行動',
                  '2026/10/23颱風休市為可靠新聞轉述，尚未在此版封存官方原始臨時休市公告',
                  '2.5A絕不覆寫2.4A～2.4F歷史檔案，也不計算報酬或勝率'],
         'outputs':['research_readiness_meta.json','research_readiness_cohorts.csv',
                    'corporate_action_gap_audit.csv','market_session_exceptions.csv']}
    dump_json(data_dir/'research_readiness_meta.json', out)
    dump_csv(data_dir/'research_readiness_cohorts.csv',cohort_rows,COHORT_COLS)
    dump_csv(data_dir/'corporate_action_gap_audit.csv',action_audit,ACTION_COLS)
    dump_csv(data_dir/'market_session_exceptions.csv',exceptions,EXCEPTION_COLS)
    print('2.5A cross-source readiness:',out['status'],'cohorts:',len(items),'rows:',len(observation_rows),
          'issues:',len(issues),'NO RETURNS')
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir',type=Path, default=DATA)
    args=p.parse_args()
    evaluate(args.data_dir)


if __name__=='__main__': main()
