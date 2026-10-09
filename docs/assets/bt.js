/* 백테스트 결과 그래프 (backtest.html) — 외부 라이브러리 0, SVG. 서식은 chart.js(종목 차트)·크립토/골드 신호 차트와 같은 어두운 판(#0b0f17)·격자(#1f2a3a)·보조 글자(#8b97a7).
   데이터: data/bt/*.json (scripts/mm_bt_data.py 가 ~/studies/mm_rotation_20261007/bt_topn/out 에서 변환). 과거 시뮬레이션이며 미래 성과를 뜻하지 않는다. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var C = { grid: '#1f2a3a', txt: '#8b97a7', bg: '#0b0f17', ink: '#e6edf3', shade: 'rgba(239,68,68,.13)' };
  /* 정책 색: 범주형 팔레트 고정 순서(validate_palette 통과, dark #0b0f17) — 색은 항목(정책)에 붙고 순위로 바뀌지 않는다 */
  var COL = { 'B3-1': '#3987e5', 'B3-3': '#d95926', 'B3-5': '#199e70', 'B3-7': '#c98500', 'B1': '#d55181', 'B2': '#9085e9', 'R2-5': '#8b97a7', 'R2-7': '#8b97a7' };
  var DASH = { 'B1': '6 3', 'B2': '6 3', 'R2-5': '2 3', 'R2-7': '2 3' };
  var VCOL = { C: '#8b97a7', H1: '#f59e0b', H2: '#3b82f6' };
  var POL = ['B1', 'B2', 'B3-1', 'B3-3', 'B3-5', 'B3-7'];
  var LAB = { 'B1': 'B1 SOXL 단독', 'B2': 'B2 보유 6종 고정', 'B3-1': 'B3-1 상위 1', 'B3-3': 'B3-3 상위 3', 'B3-5': 'B3-5 상위 5', 'B3-7': 'B3-7 상위 7', 'R2-5': 'R2-5 무작위 중앙값', 'R2-7': 'R2-7 무작위 중앙값' };
  var VL = { C: '지속(C)', H1: '신규 동결(H1)', H2: '매수 정지(H2)' };
  var st = { period: 'main', v: 'C', hidden: {} };
  var D = {}, cache = {}, META, DATES;
  var ts = function (d) { var p = d.split('-'); return Date.UTC(+p[0], +p[1] - 1, p[2] ? +p[2] : 1); };
  var f3 = function (x) { return x === null || x === undefined ? '—' : (+x).toFixed(3); };
  var f2 = function (x) { return (+x).toFixed(2); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };

  function niceTicks(lo, hi, n) {
    if (hi - lo < 1e-9) { hi = lo + 1; }
    var raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), m = raw / p;
    var s = (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p, a = Math.ceil(lo / s - 1e-9) * s, out = [];
    for (var v = a; v <= hi + 1e-9; v += s) out.push(+v.toFixed(6));
    return { t: out, lo: Math.min(lo, out[0] === undefined ? lo : out[0]), hi: Math.max(hi, out.length ? out[out.length - 1] : hi) };
  }
  function width(box) { return Math.max(300, box.clientWidth - 2); }

  /* ---------- 시간축 꺾은선 공용 ---------- */
  /* o: {box, ro(readout el), x:[날짜], series:[{k,v:[...],col,dash,w}], band:{lo,hi}|null, h, step, ymin, ymax, area:bool, fmt} */
  function lineChart(o) {
    var box = o.box, W = width(box), H = o.h || (W < 480 ? 230 : 280), L = 40, R = 10, T = 8, B = 22, pw = W - L - R, ph = H - T - B;
    var xs = o.x.map(ts), x0 = xs[0], x1 = xs[xs.length - 1], dx = Math.max(1, x1 - x0), n = xs.length, i;
    var lo = Infinity, hi = -Infinity;
    o.series.forEach(function (s) { for (i = 0; i < n; i++) { var y = s.v[i]; if (y === null || y === undefined) continue; if (y < lo) lo = y; if (y > hi) hi = y; } });
    if (o.band) for (i = 0; i < n; i++) { if (o.band.lo[i] < lo) lo = o.band.lo[i]; if (o.band.hi[i] > hi) hi = o.band.hi[i]; }
    if (o.ymin !== undefined) lo = Math.min(lo, o.ymin); if (o.ymax !== undefined) hi = Math.max(hi, o.ymax);
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    var tk = niceTicks(lo, hi, 6), X = function (t) { return L + (t - x0) / dx * pw; }, Y = function (v) { return T + (tk.hi - v) / (tk.hi - tk.lo) * ph; };
    var g = '';
    (o.shade || []).forEach(function (r) {
      var a = X(ts(r[0])), b = X(ts(r[1]) + 86400000 * 1.4); g += '<rect x="' + a.toFixed(1) + '" y="' + T + '" width="' + Math.max(1, b - a).toFixed(1) + '" height="' + ph + '" fill="' + C.shade + '"/>';
    });
    tk.t.forEach(function (v) {
      g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v).toFixed(1) + '" y2="' + Y(v).toFixed(1) + '" stroke="' + (v === 0 ? '#3a4658' : C.grid) + '" stroke-width="1"/>' +
        '<text x="' + (L - 5) + '" y="' + (Y(v) + 3.5).toFixed(1) + '" fill="' + C.txt + '" font-size="10" text-anchor="end">' + (o.fmt ? o.fmt(v) : v) + '</text>';
    });
    var y0 = new Date(x0).getUTCFullYear(), y1 = new Date(x1).getUTCFullYear(), span = y1 - y0, stp = span > 12 ? 4 : span > 6 ? 2 : 1, yy;
    for (yy = Math.ceil(y0 / stp) * stp; yy <= y1; yy += stp) {
      var xx = X(Date.UTC(yy, 0, 1)); if (xx < L + 8 || xx > W - R - 10) continue;
      g += '<line x1="' + xx.toFixed(1) + '" x2="' + xx.toFixed(1) + '" y1="' + (T + ph) + '" y2="' + (T + ph + 3) + '" stroke="' + C.txt + '"/><text x="' + xx.toFixed(1) + '" y="' + (H - 6) + '" fill="' + C.txt + '" font-size="10" text-anchor="middle">' + yy + '</text>';
    }
    var bandSvg = '';
    if (o.band) {
      var top = '', bot = '';
      for (i = 0; i < n; i++) { top += (i ? 'L' : 'M') + X(xs[i]).toFixed(1) + ' ' + Y(o.band.hi[i]).toFixed(1); }
      for (i = n - 1; i >= 0; i--) { bot += 'L' + X(xs[i]).toFixed(1) + ' ' + Y(o.band.lo[i]).toFixed(1); }
      bandSvg = '<path d="' + top + bot + 'Z" fill="' + C.txt + '" fill-opacity=".16" stroke="none"/>';
    }
    var lines = '';
    o.series.forEach(function (s) {
      var d = '', prev = null, k;
      for (i = 0; i < n; i++) {
        var y = s.v[i]; if (y === null || y === undefined || y !== y) { prev = null; continue; }
        var px = X(xs[i]).toFixed(1), py = Y(y).toFixed(1);
        if (o.step && prev !== null) d += 'L' + px + ' ' + prev; d += (prev === null ? 'M' : 'L') + px + ' ' + py; prev = py;
      }
      if (o.area) {
        var base = Y(Math.max(tk.lo, Math.min(0, tk.hi))).toFixed(1);
        lines += '<path d="' + d + 'L' + X(x1).toFixed(1) + ' ' + base + 'L' + L + ' ' + base + 'Z" fill="' + s.col + '" fill-opacity=".07" stroke="none"/>';
      }
      lines += '<path d="' + d + '" fill="none" stroke="' + s.col + '" stroke-width="' + (s.w || 1.6) + '" stroke-linejoin="round"' + (s.dash ? ' stroke-dasharray="' + s.dash + '"' : '') + '/>';
    });
    var uid = o.box.id;
    box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(o.label || '') + '"><rect width="' + W + '" height="' + H + '" fill="' + C.bg + '"/>' +
      g + bandSvg + lines + '<line id="' + uid + 'x" y1="' + T + '" y2="' + (T + ph) + '" stroke="#8b97a7" stroke-dasharray="3 3" visibility="hidden"/>' +
      '<rect id="' + uid + 'h" x="' + L + '" y="' + T + '" width="' + pw + '" height="' + ph + '" fill="transparent" style="touch-action:pan-y"/></svg>';
    var cx = $(uid + 'x'), hit = $(uid + 'h');
    function at(idx, on) {
      var xx = X(xs[idx]); cx.setAttribute('x1', xx); cx.setAttribute('x2', xx); cx.setAttribute('visibility', on ? 'visible' : 'hidden');
      var h = '<b>' + o.x[idx] + '</b>';
      o.series.forEach(function (s) { if (s.v[idx] !== null && s.v[idx] !== undefined) h += ' · <span class="sw" style="background:' + s.col + '"></span>' + esc(s.name || s.k) + ' <b>' + (o.rfmt ? o.rfmt(s.v[idx]) : f3(s.v[idx])) + '</b>'; });
      if (o.band) h += ' · 무작위 5~95% <b>' + f3(o.band.lo[idx]) + '~' + f3(o.band.hi[idx]) + '</b>';
      o.ro.innerHTML = h;
    }
    function near(clientX) {
      var rc = box.querySelector('svg').getBoundingClientRect(), t = x0 + ((clientX - rc.left) * (W / rc.width) - L) / pw * dx, lo2 = 0, hi2 = n - 1;
      while (lo2 < hi2) { var m = (lo2 + hi2) >> 1; if (xs[m] < t) lo2 = m + 1; else hi2 = m; }
      if (lo2 > 0 && Math.abs(xs[lo2 - 1] - t) < Math.abs(xs[lo2] - t)) lo2--; return lo2;
    }
    ['pointermove', 'pointerdown'].forEach(function (ev) { hit.addEventListener(ev, function (e) { at(near(e.clientX), true); }); });
    hit.addEventListener('pointerleave', function () { at(n - 1, false); });
    at(n - 1, false);
  }

  /* ---------- 범례(항목 켜기/끄기) ---------- */
  function legend(el, keys) {
    el.innerHTML = keys.map(function (k) {
      var on = !st.hidden[k];
      return '<button type="button" class="lg' + (on ? '' : ' off') + '" data-k="' + k + '" aria-pressed="' + on + '"><i style="background:' + COL[k] + '"></i>' + esc(LAB[k]) + '</button>';
    }).join('') + (el.getAttribute('data-shade') ? '<span class="lg shd"><i style="background:' + C.shade + ';border:1px solid #6b2a2a"></i>역할3 상태 4 구간</span>' : '');
  }
  function bindLegends() {
    Array.prototype.forEach.call(document.querySelectorAll('.legend'), function (el) {
      el.addEventListener('click', function (e) { var b = e.target.closest('button.lg'); if (!b) return; var k = b.getAttribute('data-k'); st.hidden[k] = !st.hidden[k]; renderAll(); });
    });
  }
  var vis = function (keys) { return keys.filter(function (k) { return !st.hidden[k]; }); };

  /* ---------- 데이터 로딩 ---------- */
  function getJ(name) {
    if (cache[name]) return Promise.resolve(cache[name]);
    return fetch('data/bt/' + name + '.json').then(function (r) { if (!r.ok) throw new Error(name); return r.json(); }).then(function (j) { cache[name] = j; return j; });
  }
  var curKey = function () { return st.period + '_' + st.v; };
  function load() {
    var key = curKey();
    return Promise.all([getJ('meta'), getJ('dates'), getJ('monthly'), getJ('yearly'), getJ('variants'), getJ('hist'), getJ('path_' + st.period + '_' + st.v)]).then(function (a) {
      if (key !== curKey()) return false;       /* 그 사이 버튼이 바뀌었으면 늦게 도착한 응답은 버린다(경로와 날짜 길이 불일치 방지) */
      META = a[0]; DATES = a[1]; D.mon = a[2]; D.yr = a[3]; D.cmp = a[4]; D.hist = a[5]; D.path = a[6]; D.key = key;
      return true;
    });
  }
  function sel() { return Array.prototype.map.call(document.querySelectorAll('[data-period],[data-var]'), function (b) { b.classList.toggle('on', b.getAttribute('data-period') === st.period || b.getAttribute('data-var') === st.v); }); }

  /* ---------- 차트 ---------- */
  function mk(keys, field, extra) {
    return vis(keys).map(function (k) { return { k: k, name: k, v: D.path[field][k], col: COL[k], dash: DASH[k], w: k === 'B3-5' ? 2.4 : 1.6 }; }).concat(extra || []);
  }
  var shade = function () { return META.g4_runs[st.period]; };
  function c1() {
    var x = DATES[st.period], p = D.path, R2 = !st.hidden['R2-5'];
    var s = mk(POL, 'real'); if (R2) s.push({ k: 'R2-5', name: 'R2-5 중앙', v: p.r2.med, col: COL['R2-5'], dash: DASH['R2-5'], w: 1.8 });
    lineChart({ box: $('c1'), ro: $('r1'), x: x, series: s, band: R2 ? { lo: p.r2.p5, hi: p.r2.p95 } : null, shade: shade(), label: '누적 실현이익', ymin: 0 });
    var last = x.length - 1, t = [];
    POL.forEach(function (k) { if (!st.hidden[k]) t.push(k + ' ' + f3(p.real[k][last])); });
    if (R2) t.push('R2-5 중앙 ' + f3(p.r2.med[last]) + ' (5~95% ' + f3(p.r2.p5[last]) + '~' + f3(p.r2.p95[last]) + ')');
    $('s1').textContent = x[last] + ' 최종 누적 실현이익: ' + t.join(' · ');
  }
  function c2() {
    var x = DATES[st.period], p = D.path;
    lineChart({ box: $('c2a'), ro: $('r2a'), x: x, series: mk(POL, 'ev'), shade: shade(), label: '평가손익 경로(실현+미실현)', h: 230, ymin: 0 });
    var dd = mk(POL, 'dd').map(function (s) { s.v = s.v.map(function (y) { return -y; }); return s; });
    lineChart({ box: $('c2b'), ro: $('r2b'), x: x, series: dd, shade: shade(), label: '낙폭', h: 170, area: true, ymax: 0, fmt: f2 });
    var last = x.length - 1, t = [];
    POL.forEach(function (k) { if (st.hidden[k]) return; var m = 0, i; for (i = 0; i < p.dd[k].length; i++) if (p.dd[k][i] > m) m = p.dd[k][i]; t.push(k + ' ' + f3(p.ev[k][last]) + ' / ' + f3(m)); });
    $('s2').textContent = x[last] + ' 평가손익 / 최대 낙폭: ' + t.join(' · ');
  }
  function c3() {
    var M = D.mon, ser = M.series[st.v], keys = vis(POL.concat(['R2-5'])), n = M.months.length;
    var series = keys.map(function (k) { return { k: k, name: k === 'R2-5' ? 'R2-5 중앙' : k, v: ser[k], col: COL[k], dash: DASH[k], w: k === 'B3-5' ? 2.4 : 1.6 }; });
    var box = $('c3'), W = width(box), H = W < 480 ? 230 : 280, L = 40, R = 10, T = 8, B = 22, pw = W - L - R, ph = H - T - B, lo = 0, hi = 0;
    series.forEach(function (s) { s.v.forEach(function (y) { if (y !== null) { lo = Math.min(lo, y); hi = Math.max(hi, y); } }); });
    var tk = niceTicks(lo, hi, 5), X = function (i) { return L + i / (n - 1) * pw; }, Y = function (v) { return T + (tk.hi - v) / (tk.hi - tk.lo) * ph; }, g = '', i;
    tk.t.forEach(function (v) { g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v).toFixed(1) + '" y2="' + Y(v).toFixed(1) + '" stroke="' + (v === 0 ? '#3a4658' : C.grid) + '"/><text x="' + (L - 5) + '" y="' + (Y(v) + 3.5).toFixed(1) + '" fill="' + C.txt + '" font-size="10" text-anchor="end">' + v + '</text>'; });
    for (i = 0; i < n; i++) if (M.months[i].slice(5) === '01' || i === 0 || i === n - 1 && W > 480) g += '<text x="' + X(i).toFixed(1) + '" y="' + (H - 6) + '" fill="' + C.txt + '" font-size="10" text-anchor="' + (i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle') + '">' + M.months[i] + '</text>';
    var lines = '';
    series.forEach(function (s) {
      var d = '', prev = false, dots = '';
      s.v.forEach(function (y, j) { if (y === null) { prev = false; return; } d += (prev ? 'L' : 'M') + X(j).toFixed(1) + ' ' + Y(y).toFixed(1); prev = true; dots += '<circle cx="' + X(j).toFixed(1) + '" cy="' + Y(y).toFixed(1) + '" r="2" fill="' + s.col + '"/>'; });
      lines += '<path d="' + d + '" fill="none" stroke="' + s.col + '" stroke-width="' + s.w + '"' + (s.dash ? ' stroke-dasharray="' + s.dash + '"' : '') + '/>' + dots;
    });
    box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="2021-11~2023-12 월별 경로"><rect width="' + W + '" height="' + H + '" fill="' + C.bg + '"/>' + g + lines +
      '<line id="c3x" y1="' + T + '" y2="' + (T + ph) + '" stroke="#8b97a7" stroke-dasharray="3 3" visibility="hidden"/><rect id="c3h" x="' + L + '" y="' + T + '" width="' + pw + '" height="' + ph + '" fill="transparent" style="touch-action:pan-y"/></svg>';
    function at(j, on) {
      var cx = $('c3x'); cx.setAttribute('x1', X(j)); cx.setAttribute('x2', X(j)); cx.setAttribute('visibility', on ? 'visible' : 'hidden');
      $('r3').innerHTML = '<b>' + M.months[j] + '</b>' + series.map(function (s) { return s.v[j] === null ? '' : ' · <span class="sw" style="background:' + s.col + '"></span>' + esc(s.name) + ' <b>' + f3(s.v[j]) + '</b>'; }).join('');
    }
    var hit = $('c3h');
    ['pointermove', 'pointerdown'].forEach(function (ev) { hit.addEventListener(ev, function (e) { var rc = box.querySelector('svg').getBoundingClientRect(); at(Math.max(0, Math.min(n - 1, Math.round(((e.clientX - rc.left) * (W / rc.width) - L) / pw * (n - 1)))), true); }); });
    hit.addEventListener('pointerleave', function () { at(n - 1, false); }); at(n - 1, false);
    var ix = function (m) { return M.months.indexOf(m); };
    $('s3').textContent = '2022-09 / 2023-12 (2021-10-29 대비): ' + keys.map(function (k) { return (k === 'R2-5' ? 'R2-5 중앙' : k) + ' ' + f3(ser[k][ix('2022-09')]) + ' / ' + f3(ser[k][ix('2023-12')]); }).join(' · ');
    var th = '<tr><th>월</th>' + keys.map(function (k) { return '<th>' + esc(k) + '</th>'; }).join('') + '</tr>';
    $('t3').innerHTML = th + M.months.map(function (m, j) { return '<tr><td>' + m + '</td>' + keys.map(function (k) { return '<td>' + f3(ser[k][j]) + '</td>'; }).join('') + '</tr>'; }).join('');
  }
  /* 묶음 막대 공용: groups=[{name, bars:[{k,v,col}]}] */
  function barChart(o) {
    var box = o.box, W = width(box), H = o.h || (W < 480 ? 230 : 270), L = 40, R = 8, T = 8, B = 24, pw = W - L - R, ph = H - T - B, lo = 0, hi = 0;
    o.groups.forEach(function (gr) { gr.bars.forEach(function (b) { if (b.v !== null) { lo = Math.min(lo, b.v); hi = Math.max(hi, b.v); } }); });
    var tk = niceTicks(lo, hi, 4), Y = function (v) { return T + (tk.hi - v) / (tk.hi - tk.lo) * ph; }, g = '', ng = o.groups.length, gw = pw / ng, i;
    tk.t.forEach(function (v) { g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v).toFixed(1) + '" y2="' + Y(v).toFixed(1) + '" stroke="' + (v === 0 ? '#3a4658' : C.grid) + '"/><text x="' + (L - 5) + '" y="' + (Y(v) + 3.5).toFixed(1) + '" fill="' + C.txt + '" font-size="10" text-anchor="end">' + v + '</text>'; });
    var bars = '';
    o.groups.forEach(function (gr, gi) {
      var nb = gr.bars.length, inner = gw * 0.78, bw = Math.max(2, inner / nb - 2), gx = L + gi * gw + (gw - inner) / 2;
      gr.bars.forEach(function (b, bi) {
        if (b.v === null) return;
        var y0 = Y(0), y1 = Y(b.v), top = Math.min(y0, y1), h = Math.max(1, Math.abs(y1 - y0));
        bars += '<rect class="bar" x="' + (gx + bi * (inner / nb)).toFixed(1) + '" y="' + top.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="1.5" fill="' + b.col + '" data-t="' + esc(gr.name + ' · ' + b.name + ' ' + f3(b.v)) + '"/>';
      });
      g += '<text x="' + (L + gi * gw + gw / 2).toFixed(1) + '" y="' + (H - 8) + '" fill="' + C.txt + '" font-size="' + (gw < 40 ? 9 : 10) + '" text-anchor="middle">' + esc(gr.short || gr.name) + '</text>';
    });
    box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(o.label) + '"><rect width="' + W + '" height="' + H + '" fill="' + C.bg + '"/>' + g + bars + '</svg>';
    Array.prototype.forEach.call(box.querySelectorAll('.bar'), function (r) {
      var f = function () { o.ro.textContent = r.getAttribute('data-t'); };
      r.addEventListener('pointerenter', f); r.addEventListener('pointerdown', f);
    });
  }
  function c4() {
    var Y = D.yr, ser = Y.series[st.v], keys = vis(POL.concat(['R2-5']));
    barChart({ box: $('c4'), ro: $('r4'), label: '연도별 실현이익', groups: Y.years.map(function (yv, j) { return { name: yv + '', bars: keys.map(function (k) { return { name: k === 'R2-5' ? 'R2-5 중앙' : k, v: ser[k][j], col: COL[k] }; }) }; }) });
    $('r4').textContent = '막대에 손을 대면 값이 여기에 표시됩니다.';
    var j22 = Y.years.indexOf(2022), j23 = Y.years.indexOf(2023);
    $('s4').textContent = '2022 / 2023 실현이익: ' + keys.map(function (k) { return (k === 'R2-5' ? 'R2-5 중앙' : k) + ' ' + f3(ser[k][j22]) + ' / ' + f3(ser[k][j23]); }).join(' · ');
    $('t4').innerHTML = '<tr><th>연도</th>' + keys.map(function (k) { return '<th>' + esc(k) + '</th>'; }).join('') + '</tr>' + Y.years.map(function (yv, j) { return '<tr><td>' + yv + '</td>' + keys.map(function (k) { return '<td>' + f3(ser[k][j]) + '</td>'; }).join('') + '</tr>'; }).join('');
  }
  var SHORT = { 'R2-5': 'R2-5', 'R2-7': 'R2-7' };
  function c5() {
    var P = D.cmp[st.period], keys = vis(POL.concat(['R2-5', 'R2-7'])), T = [['realized', '총 실현이익', 'c5a', 'r5a'], ['maxdd', '최대 낙폭', 'c5b', 'r5b'], ['min_rel_2022', '2022 최저', 'c5c', 'r5c']];
    T.forEach(function (t) {
      barChart({ box: $(t[2]), ro: $(t[3]), h: 190, label: t[1], groups: keys.map(function (k) { return { name: k === 'R2-5' || k === 'R2-7' ? k + ' 중앙' : k, short: k, bars: ['C', 'H1', 'H2'].map(function (v) { return { name: v, v: P[k][v][t[0]], col: VCOL[v] }; }) }; }) });
      $(t[3]).textContent = '막대에 손을 대면 값이 표시됩니다.';
    });
    $('s5').textContent = 'C → H1 → H2 (실현이익 / 최대 낙폭 / 2022 최저): ' + keys.map(function (k) {
      return (k.indexOf('R2') === 0 ? k + ' 중앙' : k) + ' ' + ['realized', 'maxdd', 'min_rel_2022'].map(function (m) { return ['C', 'H1', 'H2'].map(function (v) { return f3(P[k][v][m]); }).join('→'); }).join(' / ');
    }).join(' · ');
    $('t5').innerHTML = '<tr><th>정책</th><th>변형</th><th>실현이익</th><th>최대 낙폭</th><th>2022 최저</th></tr>' + keys.map(function (k) { return ['C', 'H1', 'H2'].map(function (v) { return '<tr><td>' + esc(k) + '</td><td>' + v + '</td><td>' + f3(P[k][v].realized) + '</td><td>' + f3(P[k][v].maxdd) + '</td><td>' + f3(P[k][v].min_rel_2022) + '</td></tr>'; }).join(''); }).join('');
  }
  function hist1(box, h, key, b3k, lab) {
    var d = h.dist[key], W = width(box), H = 150, L = 34, R = 8, T = 16, B = 22, pw = W - L - R, ph = H - T - B, e = h.edges, nb = d.counts.length, mx = Math.max.apply(null, d.counts);
    var tk = niceTicks(0, mx, 3), Y = function (v) { return T + (tk.hi - v) / tk.hi * ph; }, X = function (v) { return L + (v - e[0]) / (e[nb] - e[0]) * pw; }, g = '', bars = '', i;
    tk.t.forEach(function (v) { g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + Y(v).toFixed(1) + '" y2="' + Y(v).toFixed(1) + '" stroke="' + C.grid + '"/><text x="' + (L - 5) + '" y="' + (Y(v) + 3.5).toFixed(1) + '" fill="' + C.txt + '" font-size="10" text-anchor="end">' + v + '</text>'; });
    for (i = 0; i < nb; i++) bars += '<rect class="bar" x="' + (X(e[i]) + 0.5).toFixed(1) + '" y="' + Y(d.counts[i]).toFixed(1) + '" width="' + Math.max(1, X(e[i + 1]) - X(e[i]) - 1).toFixed(1) + '" height="' + (T + ph - Y(d.counts[i])).toFixed(1) + '" rx="1.5" fill="#6b7685" data-t="' + e[i].toFixed(3) + '~' + e[i + 1].toFixed(3) + ': ' + d.counts[i] + '회"/>';
    var nt = 4, lab2 = '';
    for (i = 0; i <= nt; i++) { var v = e[0] + (e[nb] - e[0]) * i / nt; lab2 += '<text x="' + X(v).toFixed(1) + '" y="' + (H - 6) + '" fill="' + C.txt + '" font-size="10" text-anchor="' + (i === 0 ? 'start' : i === nt ? 'end' : 'middle') + '">' + v.toFixed(2) + '</text>'; }
    var bx = X(d.b3), anchor = bx > L + pw * 0.6 ? 'end' : 'start';
    var mark = '<line x1="' + bx.toFixed(1) + '" x2="' + bx.toFixed(1) + '" y1="' + (T - 4) + '" y2="' + (T + ph) + '" stroke="' + COL[b3k] + '" stroke-width="2.4"/><text x="' + (bx + (anchor === 'end' ? -4 : 4)).toFixed(1) + '" y="' + (T + 6) + '" fill="' + C.ink + '" font-size="10" stroke="#0b0f17" stroke-width="3" paint-order="stroke" text-anchor="' + anchor + '">' + b3k + ' ' + f3(d.b3) + '</text>';
    box.innerHTML = '<div class="hl">' + esc(lab) + '</div><svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(lab) + '"><rect width="' + W + '" height="' + H + '" fill="' + C.bg + '"/>' + g + bars + lab2 + mark + '</svg>';
    Array.prototype.forEach.call(box.querySelectorAll('.bar'), function (r) { var f = function () { $('r6').textContent = lab + ' ' + r.getAttribute('data-t'); }; r.addEventListener('pointerenter', f); r.addEventListener('pointerdown', f); });
    return d;
  }
  function c6() {
    var H = D.hist[st.period], out = [];
    [['realized', 'r', '실현이익'], ['maxdd', 'd', '최대 낙폭']].forEach(function (m) {
      [5, 7].forEach(function (n) {
        var d = hist1($('c6' + m[1] + n), H[m[0]], n + '|' + st.v, 'B3-' + n, 'R2-' + n + ' ' + m[2] + ' 분포(1,000회)');
        out.push('R2-' + n + ' ' + m[2] + ' p5 ' + f3(d.p5) + ' · 중앙 ' + f3(d.median) + ' · p95 ' + f3(d.p95) + ', B3-' + n + ' ' + f3(d.b3) + '(≤ ' + d.pct_le.toFixed(1) + '%)');
      });
    });
    $('r6').textContent = '막대에 손을 대면 구간·횟수가 표시됩니다.';
    $('s6').textContent = out.join(' · ');
  }
  function c7() {
    var x = DATES[st.period], keys = vis(['B3-3', 'B3-5', 'B3-7']), p = D.path;
    lineChart({ box: $('c7'), ro: $('r7'), x: x, step: true, shade: shade(), label: '동시 STUCK 슬롯 수', h: 190, ymin: 0, fmt: function (v) { return v % 1 ? '' : v; }, rfmt: function (v) { return v; },
      series: keys.map(function (k) { return { k: k, name: k, v: p.stk[k], col: COL[k], w: k === 'B3-5' ? 2.2 : 1.5 }; }) });
    $('s7').textContent = '기간 중 최대 동시 STUCK 슬롯: ' + keys.map(function (k) { return k + ' ' + Math.max.apply(null, p.stk[k]); }).join(' · ');
  }
  function renderAll() {
    if (D.key !== curKey()) return;
    sel();
    ['l1', 'l2', 'l3', 'l4'].forEach(function (id) { legend($(id), POL.concat(['R2-5'])); });
    legend($('l7'), ['B3-3', 'B3-5', 'B3-7']);
    $('pnote').textContent = st.period === 'ref' ? '참고 구간 2010-01-04~: 차트 3·4 는 주 구간(2020~) 값입니다.' : '';
    c1(); c2(); c3(); c4(); c5(); c6(); c7();
  }
  function go() {
    sel();
    load().then(function (okk) { if (okk) renderAll(); }).catch(function () { var m = '<div class="chartnote">백테스트 데이터를 읽지 못했습니다(웹 주소로 여십시오).</div>'; ['c1', 'c2a', 'c3', 'c4', 'c5a', 'c7'].forEach(function (id) { if ($(id)) $(id).innerHTML = m; }); });
  }
  Array.prototype.forEach.call(document.querySelectorAll('[data-period]'), function (b) { b.addEventListener('click', function () { st.period = b.getAttribute('data-period'); go(); }); });
  Array.prototype.forEach.call(document.querySelectorAll('[data-var]'), function (b) { b.addEventListener('click', function () { st.v = b.getAttribute('data-var'); go(); }); });
  bindLegends();
  var rt; window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { if (D.path) renderAll(); }, 150); });
  go();
})();
