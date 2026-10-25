/* TPE-MFDS 2.6B: read-only charts of actual archived observations.
 * No interpolation, invented trading dates, win rates, or executable HTML from CSV.
 */
(function (root) {
  'use strict';
  function html(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }
  function numeric(v) {
    if (v === null || v === undefined || String(v).trim() === '') return null;
    var n = Number(String(v).replace(/,/g, '').trim());
    return Number.isFinite(n) ? n : null;
  }
  function validDate(v) {
    if (typeof v !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
    var d = new Date(v + 'T00:00:00Z');
    return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
  }
  function entries(rows, code, fields, percent) {
    var days = new Map(), invalid = 0, duplicate = 0;
    (Array.isArray(rows) ? rows : []).forEach(function (row) {
      if (String(row.stock_id || '') !== String(code)) return;
      var date = row.date;
      var nums = fields.map(function (k) { return numeric(row[k]); });
      if (!validDate(date) || nums.some(function (v, i) { return (v === null && (percent || i < 2)) || (v !== null && percent && (v < 0 || v > 100)); })) {
        invalid++;
        return;
      }
      if (days.has(date)) {
        duplicate++;
        return; // same stock and date must never be double-counted
      }
      var o = {date:date, source:String(row.source || ''), market:String(row.market || '')};
      fields.forEach(function (f, i) { o[f] = nums[i]; });
      days.set(date, o);
    });
    var records = Array.from(days.values()).sort(function (a, b) { return a.date.localeCompare(b.date); });
    return {records:records, invalid:invalid, duplicate:duplicate};
  }
  function flowWindow(records, n, pricePoints) {
    if (!records.length) return {ok:false, reason:'無法人歷史紀錄'};
    var last = records[records.length-1].date;
    // Use the existing actual stock price sessions as a calendar for this stock,
    // and do not mistake the last N archived rows for N consecutive sessions.
    var sessions = Array.from(new Set((Array.isArray(pricePoints) ? pricePoints : [])
      .filter(function (x) { return validDate(x.date) && x.date <= last && numeric(x.close) > 0; })
      .map(function (x) { return x.date; }))).sort().slice(-n);
    if (sessions.length < n) return {ok:false, reason:'有效價格交易日不足，無法核對'+n+'日'};
    var byDate = new Map(records.map(function (x) { return [x.date, x]; }));
    var missing = sessions.filter(function (d) { return !byDate.has(d); });
    if (missing.length) return {ok:false, reason:n+'個交易日中缺少'+missing.length+'日法人資料'};
    var sums = ['foreign_net_shares','trust_net_shares','dealer_net_shares'].map(function (field) {
      return sessions.some(function (d) { return byDate.get(d)[field] === null; }) ? null : sessions.reduce(function (total, d) { return total + byDate.get(d)[field]; }, 0);
    });
    return {ok:true, sums:sums, from:sessions[0], to:sessions[sessions.length-1], count:n};
  }
  function fmtShares(v) {
    if (v === null || !Number.isFinite(v)) return '資料不足';
    var x = v / 1000;
    return (x > 0 ? '+' : '') + x.toLocaleString('zh-TW', {maximumFractionDigits:1}) + ' 張';
  }
  function pct(v) { return Number.isFinite(v) ? v.toFixed(2) + '%' : '資料不足'; }
  function lineChart(rows, fields, names, colors, unit) {
    if (rows.length < 2) return '<p class="hint">至少需要2筆不同日期的有效來源紀錄才能繪圖。</p>';
    var width = 700, height = 192, left = 55, right = 18, top = 22, bottom = 34;
    var xDates = rows.map(function (r) { return Date.parse(r.date + 'T00:00:00Z'); });
    var lowX = Math.min.apply(null, xDates), highX = Math.max.apply(null, xDates);
    if (lowX === highX) return '<p class="hint">日期不足，無法繪圖。</p>';
    var min = Math.min.apply(null, rows.flatMap(function (r) { return fields.map(function (f) { return r[f]; }); }));
    var max = Math.max.apply(null, rows.flatMap(function (r) { return fields.map(function (f) { return r[f]; }); }));
    var padding = Math.max((max - min) * 0.14, unit === '%' ? 0.25 : 1);
    min -= padding; max += padding;
    function x(i) { return left + (xDates[i] - lowX) / (highX - lowX) * (width - left - right); }
    function y(n) { return top + (max - n) / (max - min) * (height - top - bottom); }
    var axis = '<line x1="'+left+'" y1="'+(height-bottom)+'" x2="'+(width-right)+'" y2="'+(height-bottom)+'" stroke="#98a6b5"/>'+
      '<line x1="'+left+'" y1="'+top+'" x2="'+left+'" y2="'+(height-bottom)+'" stroke="#98a6b5"/>'+
      '<text x="4" y="'+(top+5)+'" fill="#57677b" font-size="12">'+html(max.toFixed(1))+'</text>'+
      '<text x="4" y="'+(height-bottom)+'" fill="#57677b" font-size="12">'+html(min.toFixed(1))+'</text>'+
      '<text x="'+left+'" y="'+(height-10)+'" fill="#57677b" font-size="12">'+html(rows[0].date)+'</text>'+
      '<text x="'+(width-right)+'" y="'+(height-10)+'" fill="#57677b" text-anchor="end" font-size="12">'+html(rows[rows.length-1].date)+'</text>';
    var segments = fields.map(function (f, j) {
      var points = rows.map(function (r, i) { return x(i).toFixed(1)+','+y(r[f]).toFixed(1); }).join(' ');
      var dots = rows.map(function (r, i) {
        return '<circle cx="'+x(i).toFixed(1)+'" cy="'+y(r[f]).toFixed(1)+'" r="2.6" fill="'+colors[j]+'"><title>'+
          html(names[j]+' '+r.date+' '+r[f].toFixed(2)+' '+unit)+'</title></circle>';
      }).join('');
      return '<polyline points="'+points+'" fill="none" stroke="'+colors[j]+'" stroke-width="2.3" stroke-linejoin="round"/>'+dots;
    }).join('');
    var legend = names.map(function (name,i) {
      return '<span style="display:inline-flex;gap:6px;align-items:center;margin-right:14px"><i style="display:inline-block;width:14px;height:3px;background:'+colors[i]+'"></i>'+html(name)+'</span>';
    }).join('');
    return '<div style="overflow-x:auto"><svg viewBox="0 0 700 192" role="img" aria-label="'+html(names.join('、')+'歷史趨勢；日期按實際間距繪製')+'" style="width:100%;min-width:440px;max-height:240px">'+axis+segments+'</svg></div><p class="hint">'+legend+'</p>';
  }
  function table(records, fields, headers, unitFn, limit) {
    if (!records.length) return '<p class="hint">沒有符合格式的歷史紀錄。</p>';
    var head = headers.map(function (x) { return '<th>'+html(x)+'</th>'; }).join('');
    var body = records.slice(-limit).reverse().map(function (r) {
      return '<tr><td>'+html(r.date)+'</td>'+fields.map(function (f) {return '<td>'+html(unitFn(r[f]))+'</td>';}).join('')+
        '<td>'+html(r.source || '未標示')+'</td></tr>';
    }).join('');
    return '<div class="table-wrap"><table class="data-table r-table"><thead><tr><th>資料日期</th>'+head+'<th>來源</th></tr></thead><tbody>'+body+'</tbody></table></div>';
  }
  function render(flowRows, holderRows, meta, code, prices) {
    meta = meta || {};
    var f = entries(flowRows, code, ['foreign_net_shares','trust_net_shares','dealer_net_shares'], false);
    var h = entries(holderRows, code, ['holder400_pct','holder1000_pct'], true);
    var flow = f.records.slice(-120), holder = h.records.slice(-26);
    var latestPrice = (Array.isArray(prices) && prices.length) ? prices[prices.length-1].date : '';
    var flowLast = flow.length ? flow[flow.length-1].date : '';
    var holderLast = holder.length ? holder[holder.length-1].date : '';
    var flags = [];
    if (meta.historical_data_complete !== true) flags.push('歷史資料尚未完整核實');
    if (meta.flow_source_status !== 'ok') flags.push('法人來源狀態：'+String(meta.flow_source_status || '未取得'));
    if (meta.holder_source_status !== 'ok') flags.push('集保來源狀態：'+String(meta.holder_source_status || '未取得'));
    if (latestPrice && flowLast && flowLast < latestPrice) flags.push('法人日期落後於價格交易日');
    if (flow.some(function (r) {return r.dealer_net_shares===null;})) flags.push('自營商欄位部分缺值，不以零取代');
    if (f.invalid || h.invalid) flags.push('排除格式或數值異常：法人'+f.invalid+'筆、集保'+h.invalid+'筆');
    if (f.duplicate || h.duplicate) flags.push('重複日期已去重：法人'+f.duplicate+'筆、集保'+h.duplicate+'筆');
    var summ = [5,10,20].map(function (n) {
      var s = flowWindow(flow, n, prices);
      return '<tr><td>'+n+'個交易日</td><td>'+html(s.ok ? fmtShares(s.sums[0]) : '—')+'</td><td>'+
        html(s.ok ? fmtShares(s.sums[1]) : '—')+'</td><td>'+
        html(s.ok ? fmtShares(s.sums[2]) : '—')+'</td><td>'+
        html(s.ok ? s.from+' 至 '+s.to : s.reason)+'</td></tr>';
    }).join('');
    var latestHolder = holder.length ? holder[holder.length-1] : null;
    var priorHolder = holder.length > 1 ? holder[holder.length-2] : null;
    function change(k) {
      return latestHolder && priorHolder ? (latestHolder[k]-priorHolder[k]).toFixed(2)+' pp' : '資料不足';
    }
    var status = flags.length ? '<p class="hint" style="color:#936b21">'+html(flags.join('；'))+'。</p>':
      '<p class="hint">來源檔已載入；仍需按日期檢查官方原始發布資訊。</p>';
    return '<section class="r-panel r-subpanel" aria-label="2.6B法人及大戶歷史趨勢" style="margin-top:16px">'+
      '<h3>2.6B 法人每日與大戶每週歷史趨勢</h3>'+
      '<p class="hint">法人有效紀錄 '+flow.length+' 筆（最後 '+html(flowLast||'—')+'）；大戶有效紀錄 '+holder.length+
      ' 筆（最後 '+html(holderLast||'—')+'）。資料產製：'+html(meta.generated_at_taipei||'未標示')+'。未補值、未插值、不代表勝率。</p>'+status+
      '<h4>外資／投信／自營商：5、10、20 個交易日淨買賣超</h4>'+
      '<p class="hint">使用本站同股已累積的真實價格交易日逐日對照法人紀錄；任一交易日缺漏，該期間不給合計。法人日期與最新價格可能不同日。</p>'+
      '<div class="table-wrap"><table class="data-table r-table"><thead><tr><th>期間</th><th>外資</th><th>投信</th><th>自營商</th><th>核對區間／缺漏</th></tr></thead><tbody>'+summ+'</tbody></table></div>'+
      '<h4>法人每日淨買賣超趨勢</h4>'+
      lineChart(flow.slice(-26),['foreign_net_shares','trust_net_shares'],
        ['外資','投信'],['#2876ae','#b85551'],'股')+
      '<details><summary>查看最近12筆法人原始觀察</summary>'+
      table(flow,['foreign_net_shares','trust_net_shares','dealer_net_shares'],['外資（股）','投信（股）','自營商（股）'],
        function (v) {return v === null ? '資料不足' : v.toLocaleString('zh-TW',{maximumFractionDigits:0});},12)+'</details>'+
      '<h4>集保400張、1,000張持股比率</h4>'+
      '<p class="hint">最後一期：400張 '+html(latestHolder?pct(latestHolder.holder400_pct):'資料不足')+
      '、1,000張 '+html(latestHolder?pct(latestHolder.holder1000_pct):'資料不足')+
      '；相鄰兩次有效週觀察差：'+html(change('holder400_pct'))+'／'+html(change('holder1000_pct'))+
      '（週次不連續時不得解讀為單週變化）。</p>'+
      lineChart(holder,['holder400_pct','holder1000_pct'],['400張','1,000張'],['#2876ae','#17756d'],'%')+
      '<details><summary>查看最近12筆集保持股觀察</summary>'+
      table(holder,['holder400_pct','holder1000_pct'],['400張比率','1,000張比率'],pct,12)+'</details>'+
      '<p class="hint">來源：已封存法人每日／集保每週 CSV；圖中橫軸依實際日期間距繪製，不補缺漏觀察。400張與1,000張級距依來源欄位呈現，非即時資訊。</p></section>';
  }
  var api = {render:render, entries:entries, flowWindow:flowWindow, validDate:validDate};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.MFDSChipHistory = api;
})(typeof window !== 'undefined' ? window : null);
