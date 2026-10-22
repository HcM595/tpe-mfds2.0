#!/usr/bin/env python3
"""TPE-MFDS 2.4A: append-only, point-in-time *observation* archives.

Runs AFTER all 2.3.3 source calculations and BEFORE the existing Git commit.
Archives actual source bytes and observable results, never imputes publication time.
Creates one uniquely named archive per run (re-runs do not replace earlier files).
This is a data-provenance tool, NOT a performance backtest or trading system.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'site' / 'data'
REQUIRED = (
    'chip_rank.csv', 'tech_crosscheck.csv', 'chip_signals.csv',
    'official_snapshot.csv', 'chip_rank_meta.json',
    'tech_crosscheck_meta.json', 'official_meta.json',
)
OPTIONAL = ('chip_meta.json',)
TAIPEI = ZoneInfo('Asia/Taipei')
VERSION = '2.4A'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_csv_bytes(raw: bytes, filename: str) -> list[dict]:
    try:
        decoded = raw.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded, newline=""))
        if not reader.fieldnames or 'stock_id' not in reader.fieldnames:
            raise ValueError('缺少 stock_id 欄位')
        return list(reader)
    except (UnicodeError, csv.Error, ValueError) as e:
        raise ValueError(f'{filename} 格式錯誤：{e}') from e


def read_json_bytes(raw: bytes, filename: str) -> dict:
    try:
        obj = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(obj, dict):
            raise ValueError('最外層不是JSON物件')
        return obj
    except (UnicodeError, json.JSONDecodeError, ValueError) as e:
        raise ValueError(f'{filename} 格式錯誤：{e}') from e


def isodate(value) -> str | None:
    try:
        return dt.date.fromisoformat(str(value).strip()).isoformat()
    except (TypeError, ValueError):
        return None


def isonow(value) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def check_uniques(rows: list[dict], label: str):
    ids = [str(r.get('stock_id', '')).strip() for r in rows]
    if any(not re.fullmatch(r'[0-9A-Za-z]{4,8}', i) for i in ids):
        raise ValueError(f'{label} 有空白或不合規格股票代號')
    if len(ids) != len(set(ids)):
        raise ValueError(f'{label} 股票代號重複，不可封存為有效訊號')


def validate(inputs: dict[str, bytes], captured_at: dt.datetime) -> dict:
    rank = read_csv_bytes(inputs['chip_rank.csv'], 'chip_rank.csv')
    tech = read_csv_bytes(inputs['tech_crosscheck.csv'], 'tech_crosscheck.csv')
    chips = read_csv_bytes(inputs['chip_signals.csv'], 'chip_signals.csv')
    official = read_csv_bytes(inputs['official_snapshot.csv'], 'official_snapshot.csv')
    check_uniques(rank, '籌碼排名')
    check_uniques(tech, '技術驗證')
    check_uniques(chips, '籌碼訊號')
    check_uniques(official, '官方收盤快照')
    if not rank or not tech or not official:
        raise ValueError('排名、技術或官方收盤快照是空檔案')
    rank_meta = read_json_bytes(inputs['chip_rank_meta.json'], 'chip_rank_meta.json')
    tech_meta = read_json_bytes(inputs['tech_crosscheck_meta.json'], 'tech_crosscheck_meta.json')
    official_meta = read_json_bytes(inputs['official_meta.json'], 'official_meta.json')
    if rank_meta.get('status') != 'ok':
        raise ValueError('chip_rank_meta.json 未標記為 ok，本次停止封存')
    if tech_meta.get('status') not in ('ok', 'partial'):
        raise ValueError('tech_crosscheck_meta.json 狀態異常')
    if len(rank) != len(tech) or {r['stock_id'] for r in rank} != {r['stock_id'] for r in tech}:
        raise ValueError('排名與技術驗證的股票池不同')
    if len(rank) != rank_meta.get('candidate_rows') or len(rank) != tech_meta.get('rank_candidates'):
        raise ValueError('兩份統計報告與實際候選數量不一致')
    eligible = [r for r in rank if r.get('rank_status') == '可排名']
    if len(eligible) != rank_meta.get('eligible_ranked') or len(eligible) != tech_meta.get('eligible_ranked'):
        raise ValueError('排名有效數量與統計報告不一致')
    t_index = {r['stock_id']: r for r in tech}
    ranked_numbers: list[int] = []
    source_dates: set[str] = set()
    safe_rows = []
    verified = 0
    for r in rank:
        code = r['stock_id']
        t = t_index[code]
        for fld in ('rank_status', 'chip_strength_rank', 'chip_strength_score',
                    'price_asof', 'flow_asof', 'holder_asof'):
            if str(r.get(fld, '')).strip() != str(t.get(fld, '')).strip():
                raise ValueError(f'{code} 的 {fld} 在排名與技術檔不一致')
        if r.get('rank_status') == '可排名':
            date = isodate(r.get('price_asof'))
            if not date or date != isodate(r.get('flow_asof')):
                raise ValueError(f'{code} 缺少法人與價格同日資料，不能標記為可排名')
            holder_date = isodate(r.get('holder_asof'))
            if not holder_date or holder_date > date:
                raise ValueError(f'{code} 集保持股日期異常')
            score = float(r.get('chip_strength_score', 'nan'))
            if not math.isfinite(score) or not (0 <= score <= 100):
                raise ValueError(f'{code} 籌碼分數不合法')
            try:
                ranked_numbers.append(int(r['chip_strength_rank']))
            except (TypeError, ValueError) as e:
                raise ValueError(f'{code} 排名格式錯誤') from e
            source_dates.add(date)
            verified += t.get('data_status') == '可驗證'
        safe_rows.append({
            'stock_id': code, 'stock_name': r.get('stock_name', ''),
            'market': r.get('market', ''), 'ordinary_status': r.get('ordinary_status', ''),
            'rank_status': r.get('rank_status', ''), 'rank_reason': r.get('rank_reason', ''),
            'chip_strength_rank': r.get('chip_strength_rank', ''),
            'chip_strength_score': r.get('chip_strength_score', ''),
            'price_asof': r.get('price_asof', ''), 'flow_asof': r.get('flow_asof', ''),
            'holder_asof': r.get('holder_asof', ''),
            'technical_status': t.get('technical_status', ''),
            'technical_confirmed_count': t.get('technical_confirmed_count', ''),
            'technical_data_status': t.get('data_status', ''),
            'holder_structure': t.get('holder_structure', ''),
            'holder_anomaly': t.get('holder_anomaly', ''),
        })
    if sorted(ranked_numbers) != list(range(1, len(eligible) + 1)):
        raise ValueError('籌碼排名跳號或重複，拒絕封存')
    if verified != tech_meta.get('eligible_verified'):
        raise ValueError('實際可驗證數量與技術統計報告不同')
    for fname, obj in [('chip_rank_meta.json', rank_meta),
                       ('tech_crosscheck_meta.json', tech_meta),
                       ('official_meta.json', official_meta)]:
        s = obj.get('generated_at_taipei', '')
        try:
            generated = dt.datetime.fromisoformat(s)
            if generated.tzinfo is None:
                raise ValueError('缺少時區')
        except (TypeError, ValueError) as e:
            raise ValueError(f'{fname} 缺少可靠的產出時間：{s}') from e
        delta = (captured_at - generated.astimezone(dt.timezone.utc)).total_seconds()
        if not (-300 <= delta <= 14400):
            raise ValueError(f'{fname} 產出時間距本次封存超過4小時或在未來，避免封存舊輸出')
    return {
        'rank_candidates': len(rank), 'eligible_ranked': len(eligible),
        'eligible_verified': verified, 'nonranked_candidates': len(rank) - len(eligible),
        'source_price_dates': sorted(source_dates),
        'rank_status_counts': dict(Counter(r.get('rank_status', '') for r in rank)),
        'technical_status_counts': dict(Counter(t_index[r['stock_id']].get('technical_status','') for r in eligible)),
        'holder_structure_counts': dict(Counter(t_index[r['stock_id']].get('holder_structure','') for r in eligible)),
        'rows': safe_rows,
        'source_generated_at_taipei': {
            'chip_rank': rank_meta['generated_at_taipei'],
            'tech_crosscheck': tech_meta['generated_at_taipei'],
            'official_meta': official_meta['generated_at_taipei'],
        },
    }


def write_json(path: Path, obj: dict):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + '\n', encoding='utf-8')


def collect_index(archive_root: Path) -> dict:
    # Verify prior manifest hashes against the previous index, catching accidental edits.
    old_index_path = archive_root.parent / 'signal_archive_index.json'
    old = read_json_bytes(old_index_path.read_bytes(), str(old_index_path)) if old_index_path.exists() else {}
    old_digests = {x['snapshot_id']:x['snapshot_sha256'] for x in old.get('snapshots', [])
                   if x.get('snapshot_id') and x.get('snapshot_sha256')}
    entries = []
    for path in archive_root.glob('????/??/??/*/snapshot.json'):
        raw_manifest = path.read_bytes()
        item = read_json_bytes(raw_manifest, str(path))
        rel = path.relative_to(archive_root.parent).as_posix()
        if item.get('archive_format') != 1 or not item.get('captured_at_utc'):
            raise ValueError('既有封存格式不合法：' + str(path))
        snapshot_sha = digest(raw_manifest)
        if item['snapshot_id'] in old_digests and old_digests[item['snapshot_id']] != snapshot_sha:
            raise ValueError('既有快照內容遭更改：' + item['snapshot_id'])
        for name, expected in item.get('source_sha256', {}).items():
            stored = path.parent / 'inputs' / (name + '.gz' if name.endswith('.csv') else name)
            if not stored.exists():
                raise FileNotFoundError('已封存來源檔案消失：' + str(stored))
            restored = gzip.decompress(stored.read_bytes()) if name.endswith('.csv') else stored.read_bytes()
            if digest(restored) != expected:
                raise ValueError('來源檔案與封存雜湊不符：' + str(stored))
        entries.append({
            'snapshot_id': item['snapshot_id'],
            'snapshot_sha256': snapshot_sha,
            'captured_at_utc': item['captured_at_utc'],
            'source_price_dates': item['summary']['source_price_dates'],
            'eligible_ranked': item['summary']['eligible_ranked'],
            'eligible_verified': item['summary']['eligible_verified'],
            'signal_fingerprint': item['signal_fingerprint'],
            'snapshot_path': rel,
        })
    new_ids = {x['snapshot_id'] for x in entries}
    if set(old_digests) - new_ids:
        raise ValueError('先前已記錄的快照遭刪除，拒絕更新索引')
    entries.sort(key=lambda v: (v['captured_at_utc'], v['snapshot_id']))
    previously_seen = {}
    repeats = 0
    for entry in entries:
        sig = entry['signal_fingerprint']
        entry['first_seen_snapshot_id'] = previously_seen.setdefault(sig, entry['snapshot_id'])
        entry['same_signal_as_earlier_snapshot'] = entry['first_seen_snapshot_id'] != entry['snapshot_id']
        repeats += entry['same_signal_as_earlier_snapshot']
    return {
        'version': VERSION,
        'note': '同一訊號指紋的重跑要去重；每份來源快照保留原始封存時間，不覆寫舊檔。',
        'snapshots_total': len(entries),
        'unique_signal_fingerprints': len(previously_seen),
        'repeated_signal_snapshots': repeats,
        'snapshots': entries,
    }


def archive(data_dir: Path = DATA, observed_at: dt.datetime | None = None,
            run_id: str | None = None, attempt: str | None = None) -> dict:
    data_dir = Path(data_dir)
    now = observed_at or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError('封存時間不可沒有時區')
    now = now.astimezone(dt.timezone.utc)
    raw = {}
    for filename in REQUIRED:
        p = data_dir / filename
        if not p.exists():
            raise FileNotFoundError('缺少必要輸入：' + str(p))
        raw[filename] = p.read_bytes()
    for filename in OPTIONAL:
        p = data_dir / filename
        if p.exists():
            raw[filename] = p.read_bytes()
    info = validate(raw, now)
    rid = re.sub(r'[^0-9a-zA-Z_-]', '_', run_id or os.getenv('GITHUB_RUN_ID', 'local'))[:50]
    att = re.sub(r'[^0-9a-zA-Z_-]', '_', attempt or os.getenv('GITHUB_RUN_ATTEMPT', '1'))[:20]
    captured = isonow(now)
    stamp = now.strftime('%Y%m%dT%H%M%S%fZ')
    snapshot_id = f'{stamp}-run{rid}-attempt{att}'
    local = now.astimezone(TAIPEI)
    archive_root = data_dir / 'signal_archive'
    parent = archive_root / local.strftime('%Y/%m/%d')
    parent.mkdir(parents=True, exist_ok=True)
    final = parent / snapshot_id
    if final.exists():
        raise FileExistsError('封存目錄已存在，禁止覆蓋：' + str(final))
    # Fingerprint reflects only archived signal CSVs, not changing generated-at fields.
    signal_fingerprint = digest(raw['chip_rank.csv'] + b'\0' + raw['tech_crosscheck.csv'])
    summary = {k:v for k,v in info.items() if k != 'rows'}
    manifest = {
        'version': VERSION, 'archive_format': 1, 'snapshot_id': snapshot_id,
        'captured_at_utc': captured, 'captured_at_taipei': local.isoformat(timespec='microseconds'),
        'first_seen_at_utc': captured, 'signal_available_at_utc': captured,
        'source_published_at': None,
        'workflow_source_sha': os.getenv('GITHUB_SHA') or None,
        'github_run_id': rid, 'github_run_attempt': att,
        'signal_fingerprint': signal_fingerprint,
        'summary': summary,
        'source_sha256': {name:digest(content) for name,content in sorted(raw.items())},
        'price_history_sha256': (digest((data_dir/'price_history.csv').read_bytes())
                                 if (data_dir/'price_history.csv').exists() else None),
        'source_storage': ('輸入CSV逐位元gzip封存，來源JSON原樣保存；'
                           'price_history.csv僅記錄指紋，不整份每日重複封存。'),
        'signals': info['rows'],
        'data_limits': [
            '首次觀測是本系統首次封存，不代表官方首次公告時間；來源公告時間未知時留 null。',
            '訊號不可回溯到 captured_at_utc 之前，也不得視為同日收盤前可交易。',
            '非官方集保歷史鏡像及未還原除權息資料，必須在回測前獨立驗證。',
            '同一來源內容的重跑必須去重；每個訊號日期也不得重複當成獨立交易。',
            '本封存尚不包含歷史各時點證券名錄或完整還原價格，不是完整可執行回測。',
        ],
    }
    tmp = Path(tempfile.mkdtemp(prefix='.mfds-tmp-', dir=parent))
    try:
        for filename, content in raw.items():
            stored = tmp / 'inputs' / (filename + '.gz' if filename.endswith('.csv') else filename)
            stored.parent.mkdir(parents=True, exist_ok=True)
            if filename.endswith('.csv'):
                with stored.open('wb') as fh:
                    with gzip.GzipFile(filename='', mode='wb', fileobj=fh, mtime=0) as gz:
                        gz.write(content)
            else:
                stored.write_bytes(content)
        write_json(tmp/'snapshot.json', manifest)
        # Files exist before rename, so observers see either a complete snapshot or none.
        tmp.rename(final)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    idx = collect_index(archive_root)
    write_json(data_dir/'signal_archive_index.json', idx)
    last = idx['snapshots'][-1]
    newest = {
        'version': VERSION, 'status': 'ok',
        'updated_at_utc': captured, 'snapshot_id': snapshot_id,
        'snapshot_path': (final/'snapshot.json').relative_to(data_dir).as_posix(),
        'latest_snapshot': last,
        'snapshots_total': idx['snapshots_total'],
        'unique_signal_fingerprints': idx['unique_signal_fingerprints'],
        'repeated_signal_snapshots': idx['repeated_signal_snapshots'],
        'summary': summary,
        'note': ('快照在GitHub與GitHub Pages中保留，不可修改或回填過去首次觀測時間。'
                 'source_published_at未知；首次封存時間不等於來源公告時間。'),
    }
    write_json(data_dir/'signal_archive_meta.json', newest)
    print(f"2.4A archived: {snapshot_id}; ranked={summary['eligible_ranked']}; "
          f"verified={summary['eligible_verified']}; snapshots={idx['snapshots_total']}")
    return newest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='TPE-MFDS append-only point-in-time signal archive')
    parser.add_argument('--data-dir', type=Path, default=DATA)
    opts = parser.parse_args()
    archive(opts.data_dir)
