#!/usr/bin/env python3
"""Fetch the *latest* TWSE/TPEx daily close snapshots for the dashboard.

Only public, delayed exchange data are displayed. Nothing in this script computes
prediction probabilities, buy/sell advice, large-holder ownership or 20-day averages.
"""
import argparse
import csv
import datetime as dt
import io
import html
import json
import re
import time
import urllib.request
import urllib.error
from urllib.parse import urlencode
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / 'site' / 'data'
URLS = {
    '上市': 'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
    '上櫃': 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
}
TWSE_RWD = 'https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL'
TWSE_MI_RWD = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX'
TWSE_MI_EXCHANGE = 'https://www.twse.com.tw/exchangeReport/MI_INDEX'
FIELDS = ['stock_id','stock_name','sector','market','close','change_pct','volume_shares',
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
            code = first(row, 'SecuritiesCompanyCode', 'SecuritiesCode', 'Code', 'SecuritiesNo')
            name = first(row, 'CompanyName', 'SecuritiesCompanyName', 'SecuritiesName', 'SecurityName', 'Name')
            close = number(first(row, 'Close', 'ClosingPrice', 'Closing'))
            amount = number(first(row, 'TransactionAmount', 'TradeValue', 'TradingAmount', 'TradingValue', 'TradeAmount'))
            day = iso_date(first(row, 'Date'))
            change = number(first(row, 'Change'))
        volume = number(first(row, 'TradeVolume', 'TradingShares', 'TradingVolume', 'TradeShares'))
        if not is_common_four_digit(code) or not name or close is None or close <= 0 or not day:
            continue
        # Only use an actual close and a known date. The daily trade amount is
        # not a 20-day average, which stays empty until we build history.
        out = dict.fromkeys(FIELDS, '')
        out.update(stock_id=code, stock_name=name, sector='未分類', market=market,
                   close=f'{close:.4f}'.rstrip('0').rstrip('.'), asof=day)
        if amount is not None and amount >= 0:
            out['trade_value_twd'] = str(int(amount))
        if volume is not None and volume >= 0:
            out['volume_shares'] = str(int(volume))
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



def normalize_twse_field(value):
    """Compare exchange-supplied column *names*, never guessed positions."""
    value = html.unescape(str(value))
    value = re.sub(r'<[^>]*>', '', value)
    value = re.sub(r'[\s\u3000]', '', value)
    return value.replace('（', '(').replace('）', ')').replace('＋', '+').replace('－', '-')


def transform_twse_rwd(payload):
    """Read STOCK_DAY_ALL or MI_INDEX (tables or fields9/data9).

    Source *response* date is mandatory; query date must never become trade date.
    All mandatory columns must be found by name, not assumed array indices.
    """
    if not isinstance(payload, dict):
        raise ValueError('TWSE盤後報表不是JSON物件')
    if str(payload.get('stat', '')).upper() != 'OK':
        raise ValueError('TWSE盤後回應stat非OK: ' + str(payload.get('stat', 'missing'))[:100])
    report_date = iso_date(payload.get('date'))
    if not report_date:
        raise ValueError('TWSE盤後報表缺少有效回應日期（不使用查詢日期代替）')

    blocks = []
    if isinstance(payload.get('tables'), list):
        blocks.extend(payload['tables'])
    # Older exchangeReport/MI_INDEX exposes fields9/data9; some records also
    # provide top-level fields/data. Parse every compatible table by names.
    for suffix in ('', *[str(i) for i in range(1, 30)]):
        fields_key = 'fields' + suffix
        data_key = 'data' + suffix
        if isinstance(payload.get(fields_key), list) and isinstance(payload.get(data_key), list):
            blocks.append({'fields': payload[fields_key], 'data': payload[data_key]})

    parsed = {}
    recognized_tables = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        fields = [normalize_twse_field(f) for f in (block.get('fields') or [])]

        def col(*candidates):
            for candidate in candidates:
                normalized = normalize_twse_field(candidate)
                if normalized in fields:
                    return fields.index(normalized)
            return None

        code_i = col('證券代號', '證券代碼', '股票代號', '代號')
        name_i = col('證券名稱', '股票名稱', '名稱')
        close_i = col('收盤價', '收盤')
        value_i = col('成交金額', '成交值')
        volume_i = col('成交股數', '成交量')
        date_i = col('日期', '交易日期')
        sign_i = col('漲跌(+/-)', '漲跌符號')
        diff_i = col('漲跌價差', '漲跌')
        mandatory = (code_i, name_i, close_i, value_i, volume_i)
        if any(i is None for i in mandatory):
            continue
        recognized_tables += 1

        for rec in block.get('data') or []:
            if not isinstance(rec, (tuple, list)) or max(mandatory) >= len(rec):
                continue
            code = str(rec[code_i]).strip()
            name = re.sub(r'<[^>]*>', '', html.unescape(str(rec[name_i]))).strip()
            close = number(rec[close_i])
            volume = number(rec[volume_i])
            amount = number(rec[value_i])
            date = (iso_date(rec[date_i]) if date_i is not None and date_i < len(rec)
                    else report_date)
            if not is_common_four_digit(code) or not name or close is None or close <= 0:
                continue
            if date != report_date:
                continue
            if volume is None or volume < 0 or amount is None or amount < 0:
                continue  # rankings need both shares and NT$ turnover
            row = dict.fromkeys(FIELDS, '')
            row.update(stock_id=code, stock_name=name, market='上市', sector='未分類',
                       close=f'{close:.4f}'.rstrip('0').rstrip('.'),
                       volume_shares=str(int(volume)), trade_value_twd=str(int(amount)),
                       asof=report_date)
            if diff_i is not None and diff_i < len(rec):
                diff = number(re.sub(r'<[^>]*>', '', html.unescape(str(rec[diff_i]))))
                if diff is not None:
                    if sign_i is not None and sign_i < len(rec):
                        sign = normalize_twse_field(rec[sign_i])
                        if sign in ('-', '−', '▼'):
                            diff = -abs(diff)
                        elif sign in ('+', '▲'):
                            diff = abs(diff)
                        else:
                            diff = None  # uncertain sign: keep daily change blank
                    else:
                        diff = None
                    if diff is not None and close - diff > 0:
                        row['change_pct'] = f'{diff / (close - diff) * 100:.4f}'
            previous = parsed.get(code)
            if previous and previous != row:
                raise ValueError('TWSE報表股票代號重複但內容衝突: ' + code)
            parsed[code] = row

    # A page about indices, not stocks, must never overwrite real stock prices.
    if not recognized_tables:
        raise ValueError('TWSE回應沒有辨識出具證券代號/名稱/收盤/成交股數/成交金額的表格')
    if len(parsed) < 700:
        raise ValueError(f'TWSE報表安全解析的上市股票過少：{len(parsed)}筆（最低700筆）')
    return list(parsed.values())


def rwd_url(target_date, endpoint=TWSE_RWD):
    dt.date.fromisoformat(target_date)
    params = {'date': target_date.replace('-', ''), 'response': 'json'}
    if endpoint in (TWSE_MI_RWD, TWSE_MI_EXCHANGE):
        params['type'] = 'ALLBUT0999'
    return endpoint + '?' + urlencode(params)


def _preview_bytes(raw):
    preview = raw[:180].decode('utf-8', errors='replace')
    return re.sub(r'\s+', ' ', preview).strip()[:130]


def get_json(url, attempts=3):
    """Raise an actionable error; never silently accept HTML as JSON."""
    error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                               '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
                'Accept': 'application/json,text/plain,*/*',
                'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.5',
            })
            with urllib.request.urlopen(request, timeout=25) as response:
                status = response.getcode()
                content_type = response.headers.get('Content-Type', '')
                raw = response.read()
            try:
                return json.loads(raw.decode('utf-8-sig'))
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError('HTTP ' + str(status) + '; Content-Type=' +
                                 content_type[:65] + '; ' + str(len(raw)) + ' bytes; '
                                 'non-JSON preview=' + repr(_preview_bytes(raw))) from exc
        except urllib.error.HTTPError as exc:
            raw = exc.read(220)
            error = ('HTTP ' + str(exc.code) + '; Content-Type=' +
                     str(exc.headers.get('Content-Type', ''))[:65] + '; preview=' +
                     repr(_preview_bytes(raw)))
        except Exception as exc:
            error = str(exc)
        if attempt < attempts - 1:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(error)


def run(twse_fixture=None, tpex_fixture=None, output_dir=DATA):
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped = {}
    meta = {
        'status': 'unavailable',
        'generated_at_taipei': dt.datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds'),
        'markets': {},
        'sources': {**URLS, '上市盤後備援': TWSE_RWD,
                    '上市MI_INDEX備援': TWSE_MI_RWD, '上市MI_INDEX舊路徑': TWSE_MI_EXCHANGE},
        'notes': ('各市場顯示各自已驗證的收盤日期。日期不同不當作同步行情；'
                  '籌碼強度排名只在法人與股價日期一致時給分。非即時報價。'),
    }
    for market,fixture in [('上市',twse_fixture),('上櫃',tpex_fixture)]:
        try:
            records=json.loads(Path(fixture).read_text(encoding='utf-8')) if fixture else get_json(URLS[market])
            rows=transform(records,market)
            if not rows:raise ValueError('官方來源沒有有效價格與日期')
            grouped[market]=rows
            meta['markets'][market]={'status':'ok','rows':len(rows),'date':rows[0]['asof'],'source':'openapi'}
        except Exception as exc:
            meta['markets'][market]={'status':'failed','error':str(exc)[:180]}
            print('WARNING ['+market+']:',exc)

    # Official fallback chain: all attempts use TWSE endpoints, and only accept
    # a result with a *response-provided* trade date newer than current TWSE.
    # Missing data, anti-bot HTML or network failures remain explicit diagnostics.
    if not twse_fixture and not tpex_fixture:
        tw = meta['markets'].get('上市', {})
        otc = meta['markets'].get('上櫃', {})
        if otc.get('date') and (not tw.get('date') or tw['date'] < otc['date']):
            target = otc['date']
            alternative = {'attempted': True, 'requested_date': target,
                           'result': 'failed', 'attempts': []}
            meta['twse_alternative'] = alternative
            endpoints = [
                ('STOCK_DAY_ALL_RWD', TWSE_RWD),
                ('MI_INDEX_RWD', TWSE_MI_RWD),
                ('MI_INDEX_exchangeReport', TWSE_MI_EXCHANGE),
            ]
            current_date = tw.get('date', '')
            for label, endpoint in endpoints:
                url = rwd_url(target, endpoint)
                attempt = {'name': label, 'url': url}
                alternative['attempts'].append(attempt)
                try:
                    rows = transform_twse_rwd(get_json(url, attempts=2))
                    actual = rows[0]['asof']
                    attempt['response_date'] = actual
                    attempt['rows'] = len(rows)
                    # Prevent accepting a truncated market-wide feed as a full snapshot.
                    baseline_count = tw.get('rows', 0)
                    if baseline_count and len(rows) < 0.85 * baseline_count:
                        attempt['result'] = 'insufficient_market_coverage'
                        attempt['error'] = ('本次僅'+str(len(rows))+'筆，原OpenAPI有'+
                                            str(baseline_count)+'筆（低於85%安全門檻）')
                        continue
                    if actual <= current_date or actual > target:
                        attempt['result'] = 'date_not_newer_or_after_target'
                        continue
                    attempt['result'] = 'selected'
                    alternative['result'] = 'selected'
                    alternative['selected_source'] = label
                    alternative['response_date'] = actual
                    grouped['上市'] = rows
                    meta['markets']['上市'] = {'status': 'ok', 'rows': len(rows),
                                               'date': actual, 'source': label}
                    break
                except Exception as exc:
                    attempt['result'] = 'failed'
                    attempt['error'] = (type(exc).__name__ + ': ' + str(exc))[:350]
                    print('WARNING [上市官方備援' + label + ']:', exc)
            if alternative['result'] != 'selected':
                alternative['error'] = '所有官方備援未取得更新日期的有效上市行情；詳細原因見attempts。'

    # If exactly one source fails completely, keep a *clearly dated* previously
    # published market snapshot instead of silently deleting an entire market.
    # This does NOT make stale prices eligible for an unmatched-date chip ranking.
    if len(grouped) < 2:
        oldfile = output_dir / 'official_snapshot.csv'
        if oldfile.exists():
            try:
                with oldfile.open(encoding='utf-8-sig', newline='') as fh:
                    previous = list(csv.DictReader(fh))
                for market, floor in [('上市', 700), ('上櫃', 600)]:
                    if market in grouped:
                        continue
                    candidates = [r for r in previous
                                  if r.get('market') == market
                                  and is_common_four_digit(r.get('stock_id', ''))
                                  and iso_date(r.get('asof'))
                                  and number(r.get('close')) is not None
                                  and number(r.get('close')) > 0]
                    if candidates:
                        old_date = max(r['asof'] for r in candidates)
                        candidates = [r for r in candidates if r['asof'] == old_date]
                    if len(candidates) < floor or len({r['stock_id'] for r in candidates}) != len(candidates):
                        continue
                    grouped[market] = [{f: r.get(f, '') for f in FIELDS} for r in candidates]
                    old_error = meta['markets'].get(market, {}).get('error', '')
                    meta['markets'][market] = {
                        'status': 'stale', 'rows': len(candidates), 'date': old_date,
                        'source': 'previous_snapshot', 'fetch_error': old_error,
                    }
                    print('WARNING [' + market + ']: 保留舊行情 ' + old_date)
            except (OSError, csv.Error, ValueError) as exc:
                meta['previous_snapshot_error'] = str(exc)[:180]

    output=[row for market in ('上市','上櫃') for row in grouped.get(market,[])]
    dates={market:items[0]['asof'] for market,items in grouped.items() if items}
    meta['market_dates']=dates
    meta['markets_included']=sorted(dates)
    meta['display_date']=max(dates.values()) if dates else None
    meta['aligned']=len(dates)==2 and len(set(dates.values()))==1
    source_stale = any(m.get('status') == 'stale' for m in meta['markets'].values())
    meta['status'] = ('ok' if meta['aligned'] and not source_stale else
                      ('partial' if output else 'unavailable'))
    meta['tracked_symbols_found']={code:any(r['stock_id']==code for r in output)
                                   for code in ('8064','3533','2345','2330')}
    if output:
        buf=io.StringIO(newline='')
        writer=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator='\n')
        writer.writeheader();writer.writerows(output)
        (output_dir/'official_snapshot.csv').write_text(buf.getvalue(),encoding='utf-8-sig')
    else:
        old=output_dir/'official_snapshot.csv'
        if old.exists():
            with old.open(encoding='utf-8-sig',newline='') as fh:
                oldrows=list(csv.DictReader(fh))
            if oldrows:
                meta['status']='stale'
                olddates=[x.get('asof','') for x in oldrows if iso_date(x.get('asof'))]
                meta['display_date']=max(olddates) if olddates else 'unknown'
                meta['markets_included']=sorted(set(x.get('market','') for x in oldrows))
                meta['market_dates']={market:max(x.get('asof','') for x in oldrows if x.get('market')==market)
                                      for market in meta['markets_included']}
                meta['notes']+=' 本次兩個市場皆未取到資料，保留已驗證的舊快照。'
    (output_dir/'official_meta.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f"Result: {meta['status']} | {len(output)} records | {meta.get('market_dates',{})}")
    return meta,output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--twse-fixture', help='Offline TWSE JSON fixture (testing only)')
    parser.add_argument('--tpex-fixture', help='Offline TPEx JSON fixture (testing only)')
    parser.add_argument('--output-dir', type=Path, default=DATA)
    args = parser.parse_args()
    run(args.twse_fixture, args.tpex_fixture, args.output_dir)
