#!/usr/bin/env python3
"""Fetch the *latest* TWSE/TPEx daily close snapshots for the dashboard.

Only public, delayed exchange data are displayed. Nothing in this script computes
prediction probabilities, buy/sell advice, large-holder ownership or 20-day averages.
"""
import argparse
import csv
import datetime as dt
import io
import json
import re
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'site' / 'data'
URLS = {
    '上市': 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
    '上櫃': 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
}
FIELDS = ['stock_id','stock_name','sector','market','close','change_pct',
          'trade_value_twd','avg_trade_value_twd','asof','large_holder_pct',
          'large_holder_change_pp','foreign_5d_net_twd',
          'M1','M2','M3','I1','I2','I3','F1','F2','F3','S1','S2','S3']


def number(s):
    try:
        a = str(s).strip().replace(',', '')
        if not a or a in {'--', '---', '----', 'X', '—', '－'}:
            return None
        v = float(a)
        return v if v == v and abs(v) != float('inf') else None
    except (ValueError, TypeError):
        return None


def iso_date(v):
    s = str(v or '').strip()
    try:
        if re.fullmatch(r'\d{7}', s):  # ROC YYYMMDD
            return dt.date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:])).isoformat()
        if re.fullmatch(r'\d{3}/\d\d/\d\d', s):
            return dt.date(int(s[:3]) + 1911, int(s[4:6]), int(s[7:])).isoformat()
        if re.fullmatch(r'\d{8}', s):
            return dt.date(int(s[:4]), int(s[4:6]), int(s[6:])).isoformat()
        return dt.date.fromisoformat(s).isoformat()
    except (ValueError, TypeError):
        return None


def is_common_four_digit(code):
    # Conservative common-stock *candidate* filter; not a security master.
    return bool(re.fullmatch(r'[1-9]\d{3}', code))


def first(row, *names):
    for key in names:
        value = row.get(key)
        if value is not None and str(value).strip() != '':
            return str(value).strip()
    return ''


def transform(records, market):
    parsed = []
    if not isinstance(records, list):
        raise ValueError('來源 JSON 並非陣列')
    for row in records:
        if not isinstance(row, dict):
            continue
        if market == '上市':
            code = first(row, 'Code'); name = first(row, 'Name')
            close = number(first(row, 'ClosingPrice'))
            amount = number(first(row, 'TradeValue'))
            day = iso_date(first(row, 'Date'))
            change = number(first(row, 'Change'))
        else:
            code = first(row, 'SecuritiesCompanyCode', 'SecuritiesCode')
            name = first(row, 'CompanyName', 'SecuritiesCompanyName', 'SecuritiesName', 'SecurityName')
            close = number(first(row, 'Close', 'ClosingPrice'))
            amount = number(first(row, 'TransactionAmount', 'TradeValue', 'TradingAmount'))
            day = iso_date(first(row, 'Date'))
            change = number(first(row, 'Change'))
        if not is_common_four_digit(code) or not name or close is None or close <= 0 or not day:
            continue
        # Only use an actual close and a known date. The daily trade amount is
        # not a 20-day average, which stays empty until we build history.
        out = dict.fromkeys(FIELDS, '')
        out.update(stock_id=code, stock_name=name, sector='未分類', market=market,
                   close=f'{close:.4f}'.rstrip('0').rstrip('.'), asof=day)
        if amount is not None and amount >= 0:
            out['trade_value_twd'] = str(int(amount))
        # For displayed daily price % change, yesterday close = today - delta.
        # These endpoints usually supply the *point* change, not percentage.
        if change is not None and close - change > 0:
            out['change_pct'] = f'{change / (close-change) * 100:.4f}'
        parsed.append(out)
    # All records should have same latest date; avoid mixing old isolated rows.
    if parsed:
        newest = max(x['asof'] for x in parsed)
        parsed = [x for x in parsed if x['asof'] == newest]
    return parsed


def get_json(url, attempts=3):
    error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; MFDS-Research-Dashboard/0.2)',
                'Accept': 'application/json',
            })
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except Exception as exc:
            error = exc
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(str(error))


def run(twse_fixture=None, tpex_fixture=None, output_dir=DATA):
    output_dir.mkdir(parents=True, exist_ok=True)
    output = []
    meta = {
        'status': 'unavailable',
        'generated_at_taipei': dt.datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
        'markets': {},
        'sources': URLS,
        'notes': '最新收盤價與當日成交額，不代表即時報價；無大戶資料與經驗驗證預測。',
    }
    for market, fixture in [('上市', twse_fixture), ('上櫃', tpex_fixture)]:
        try:
            records = json.loads(Path(fixture).read_text(encoding='utf-8')) if fixture else get_json(URLS[market])
            rows = transform(records, market)
            if not rows:
                raise ValueError('回傳資料中沒有有效普通股候選資料')
            meta['markets'][market] = {'status': 'ok', 'rows': len(rows), 'date': rows[0]['asof']}
            output.extend(rows)
        except Exception as exc:
            meta['markets'][market] = {'status': 'failed', 'error': str(exc)[:180]}
            print(f'WARNING [{market}]: {exc}')
    success = [s for s in meta['markets'].values() if s['status'] == 'ok']
    meta['status'] = ('ok' if len(success) == 2 else 'partial') if success else 'unavailable'
    # Avoid serving different trading days as if they were a synchronized snapshot.
    if success:
        common_day = max(s['date'] for s in success)
        filtered = [r for r in output if r['asof'] == common_day]
        if not filtered:
            meta['status'] = 'unavailable'
        output = filtered
        meta['display_date'] = common_day
        meta['markets_included'] = sorted(set(r['market'] for r in output))
        if len(meta['markets_included']) < 2:
            meta['status'] = 'partial'
    if output:
        buf = io.StringIO(newline='')
        writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader(); writer.writerows(output)
        (output_dir / 'official_snapshot.csv').write_text(buf.getvalue(), encoding='utf-8-sig')
    else:
        # Fail closed: never leave an old file mislabeled as new.
        (output_dir / 'official_snapshot.csv').unlink(missing_ok=True)
    (output_dir / 'official_meta.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Result: {meta['status']} | {len(output)} records | {meta.get('display_date', 'N/A')}")
    return meta, output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--twse-fixture', help='Offline TWSE JSON fixture (testing only)')
    parser.add_argument('--tpex-fixture', help='Offline TPEx JSON fixture (testing only)')
    parser.add_argument('--output-dir', type=Path, default=DATA)
    args = parser.parse_args()
    run(args.twse_fixture, args.tpex_fixture, args.output_dir)
