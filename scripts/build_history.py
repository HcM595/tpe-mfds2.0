#!/usr/bin/env python3
"""Append verified daily exchange snapshots to a bounded, self-hosted price history.

Raw daily files are committed to GitHub. The aggregated CSV is built for Pages
and NOT committed, avoiding quadratic git repository growth.
"""
import argparse
import csv
import datetime as dt
import io
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ARCHIVE = BASE / 'history_data'
SITE_DATA = BASE / 'site' / 'data'
COLUMNS = ('date', 'stock_id', 'close', 'volume_shares', 'trade_value_twd')
KEEP_DAYS = 160  # latest 160 trade dates; no adjustment for dividends or splits


def rows_from_snapshot(snapshot):
    if not snapshot.exists():
        return []
    with snapshot.open('r', encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for row in rows:
        try:
            dt.date.fromisoformat(row['asof'])
            val = float(row['close'])
            if val <= 0:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        out.append(dict(date=row['asof'], stock_id=row['stock_id'], close=row['close'],
                        volume_shares=row.get('volume_shares', ''),
                        trade_value_twd=row.get('trade_value_twd', '')))
    return out


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    content = buf.getvalue()
    if not path.exists() or path.read_text(encoding='utf-8') != content:
        path.write_text(content, encoding='utf-8')
        return True
    return False


def build(snapshot, archive=ARCHIVE, site_data=SITE_DATA, keep=KEEP_DAYS):
    archive.mkdir(parents=True, exist_ok=True)
    site_data.mkdir(parents=True, exist_ok=True)
    new_rows = rows_from_snapshot(snapshot)
    # A valid snapshot may contain different TWSE / TPEx dates. Persist each
    # verified stock to the ACTUAL trade date, never to one falsely shared date.
    # Merge with existing day files, preventing omission on an exchange outage.
    grouped = {}
    for row in new_rows:
        grouped.setdefault(row['date'], []).append(row)
    for trade_date, day_rows in sorted(grouped.items()):
        path = archive / f'{trade_date}.csv'
        existing = []
        if path.exists():
            with path.open(encoding='utf-8-sig', newline='') as fh:
                existing = list(csv.DictReader(fh))
        by_id = {row['stock_id']: row for row in existing}
        by_id.update({row['stock_id']: row for row in day_rows})
        write_csv(path, [by_id[k] for k in sorted(by_id)])
    dates = sorted(p for p in archive.glob('????-??-??.csv') if valid_date(p.stem))
    for old in dates[:-keep]:
        old.unlink()
    dates = dates[-keep:]
    history = []
    for path in dates:
        with path.open('r', encoding='utf-8-sig', newline='') as fh:
            history.extend(csv.DictReader(fh))
    write_csv(site_data / 'price_history.csv', history)
    print(f'Historical sessions: {len(dates)} | rows: {len(history)} | latest: {dates[-1].stem if dates else "none"}')
    return history


def valid_date(date_str):
    try:
        dt.date.fromisoformat(date_str)
        return True
    except ValueError:
        return False


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--snapshot', type=Path, default=SITE_DATA / 'official_snapshot.csv')
    ap.add_argument('--archive', type=Path, default=ARCHIVE)
    ap.add_argument('--site-data', type=Path, default=SITE_DATA)
    args = ap.parse_args()
    build(args.snapshot, args.archive, args.site_data)
