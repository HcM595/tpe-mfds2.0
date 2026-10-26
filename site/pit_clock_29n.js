/* TPE-MFDS 2.9N — F2/F3 three independent clocks. Not a backtest eligibility certification. */
(function (root) {
  'use strict';
  function csvRows(input) {
    const text = String(input || '').replace(/^\uFEFF/, '');
    const rows = []; let row = [], cell = '', quoted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (c === '"') {
        if (quoted && text[i + 1] === '"') { cell += '"'; i++; }
        else quoted = !quoted;
      } else if (c === ',' && !quoted) { row.push(cell); cell = ''; }
      else if ((c === '\n' || c === '\r') && !quoted) {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(cell);
        if (row.some(x => x !== '')) rows.push(row);
        row = []; cell = '';
      } else cell += c;
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    const header = rows.shift() || [];
    return rows.map(r => Object.fromEntries(header.map((k, i) => [k, r[i] ?? ''])));
  }
  function examine(row, factor) {
    const prefix = factor === 'F3' ? 'F3' : 'F2';
    const report = row?.[prefix + '_source_report_date'] || '';
    const observed = row?.[prefix + '_observed_first_at_utc'] || '';
    const publication = row?.[prefix + '_publication_at_utc'] || '';
    const gate = row?.[prefix + '_usable_for_backtest'] === 'true';
    const status = row?.[prefix + '_pit_status'] || '';
    const price = row?.price_asof || '';
    const warnings = [];
    if (!report) warnings.push('報表所屬日未取得');
    if (!observed) warnings.push('首次封存時刻未取得');
    if (!publication) warnings.push('官方公布時刻未獨立核實');
    if (report && price && report > price) warnings.push('報表所屬日晚於價格基準日');
    if (observed && price && observed.slice(0, 10) > price) warnings.push('首次封存日晚於價格基準日（UTC日）');
    if (!gate) warnings.push('不具歷史回測資格');
    return {factor:prefix, report, observed, publication, status, price, gate, warnings};
  }
  function mountTable(element, record) {
    if (!element) return;
    element.replaceChildren();
    const heading = document.createElement('h3');
    heading.textContent = '2.9N｜F2／F3 三時鐘歷史來源驗證';
    element.append(heading);
    const note = document.createElement('p');
    note.textContent = '報表所屬日 ≠ 本站首次取得UTC時刻 ≠ 官方正式公布時刻。前兩項即使早於股價日，也無法代替官方公告證明。';
    element.append(note);
    if (!record) {
      const p = document.createElement('p');
      p.textContent = '此股沒有三時鐘稽核資料；不得推定具有歷史回測資格。';
      element.append(p); return;
    }
    const baseline = document.createElement('p');
    baseline.textContent = '價格基準日：' + (record.price_asof || '缺漏') + '；目前僅顯示已封存的原始來源版本資訊。';
    element.append(baseline);
    const wrapper = document.createElement('div');
    wrapper.style.overflowX = 'auto';
    const table = document.createElement('table');
    table.style.minWidth = '790px';
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    const headings = ['因子','來源報表所屬日','本站首次取得（UTC）','官方公布時刻（UTC）','歷史回測資格／阻擋原因'];
    const thead = document.createElement('thead'), hrow = document.createElement('tr');
    for (const h of headings) { const th = document.createElement('th'); th.textContent = h; th.style.padding = '8px'; th.style.textAlign = 'left'; hrow.append(th); }
    thead.append(hrow); table.append(thead);
    const tbody = document.createElement('tbody');
    for (const name of ['F2', 'F3']) {
      const item = examine(record, name), tr = document.createElement('tr');
      const status = item.gate && item.publication ? '該筆來源標記可用（仍需其他回測條件）' : '不可作歷史回測';
      const cells = [name, item.report || '缺漏', item.observed || '缺漏', item.publication || '未驗證／不可倒填', status + '；' + (item.warnings.join('；') || item.status || '請核實完整來源')];
      for (const value of cells) { const td = document.createElement('td'); td.textContent = value; td.style.padding = '9px'; td.style.borderTop = '1px solid #dfe7ee'; td.style.verticalAlign = 'top'; tr.append(td); }
      tbody.append(tr);
    }
    table.append(tbody); wrapper.append(table); element.append(wrapper);
    const reminder = document.createElement('p');
    reminder.textContent = '本站首次取得時間不可倒推為正式公告時間。完整12因子、除權息價格、盤中截止時點與獨立回測未通過前，模型分數和勝率仍停用。';
    element.append(reminder);
  }
  let cache = null;
  async function load() {
    if (!cache) {
      cache = fetch('./data/pit_f2f3_stock_29f.csv', {cache: 'no-store'}).then(async r => {
        if (!r.ok) throw Error('三時鐘資料檔讀取失敗（HTTP ' + r.status + '）');
        return new Map(csvRows(await r.text()).filter(r => r.stock_id).map(r => [r.stock_id, r]));
      }).catch(e => { cache = null; throw e; });
    }
    return cache;
  }
  async function render(stockId, element) {
    if (!element) return;
    element.dataset.pitStockId = stockId;
    element.textContent = '正在讀取F2／F3三時鐘來源…';
    try {
      const rows = await load();
      if (element.dataset.pitStockId !== stockId) return;
      mountTable(element, rows.get(stockId));
    } catch (e) {
      if (element.dataset.pitStockId === stockId) element.textContent = '三時鐘證據讀取失敗：' + e.message + '。不可視為已驗證。';
    }
  }
  const api = {csvRows, examine, render};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.MFDSPitClock = api;
})(typeof window !== 'undefined' ? window : null);
