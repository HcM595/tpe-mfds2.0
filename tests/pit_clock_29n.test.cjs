const assert = require('node:assert/strict');
const { csvRows, examine } = require('../site/pit_clock_29n.js');
const input = '\uFEFFstock_id,price_asof,F2_source_report_date,F2_observed_first_at_utc,F2_publication_at_utc,F2_pit_status,F2_usable_for_backtest,F3_source_report_date,F3_observed_first_at_utc,F3_publication_at_utc,F3_pit_status,F3_usable_for_backtest\n' +
  '8064,2026-10-22,2026-10-22,2026-10-26T13:05:13+00:00,,first_observed_after_price_cutoff,false,2026-10-25,2026-10-26T13:05:13+00:00,,source_report_after_price,false\n';
const [row] = csvRows(input);
assert.equal(row.stock_id, '8064');
const f2 = examine(row, 'F2'), f3 = examine(row, 'F3');
assert.equal(f2.report, '2026-10-22');
assert.equal(f2.publication, '');
assert.equal(f2.gate, false);
assert(f2.warnings.includes('官方公布時刻未獨立核實'));
assert(f2.warnings.includes('不具歷史回測資格'));
assert(f2.warnings.some(x => x.includes('首次封存日晚於價格基準日')));
assert(f3.warnings.some(x => x.includes('報表所屬日晚於價格基準日')));
assert.equal(examine({},'F3').gate, false);
assert.deepEqual(csvRows('stock_id,name\n2330,"Alpha, ""Beta"""\n')[0], {stock_id:'2330',name:'Alpha, "Beta"'});
console.log('PASS 2.9N: PIT dates are not publication timestamps and future reports stay blocked');
