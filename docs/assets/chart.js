/* 종목 페이지 M-score·순위 추이 차트 — 선 2개(M-score 좌축, 순위 우축·역순), 기간 버튼 3개월·6개월·1년·전체.
   크립토/골드 시그널 리포트 차트 서식(어두운 판 #0b0f17, 격자 #1f2a3a, 앰버·블루 이중 축)을 따르되 외부 라이브러리 없이 SVG 로 그린다.
   데이터: data/series/<티커>.json = {t, d:[날짜], m:[M-score], r:[순위], n:[그날 모집단 수]} (일일 산출 말미에 scores CSV 에서 생성). */
(function () {
  'use strict';
  var box = document.getElementById('chart');
  if (!box) return;
  var T = box.getAttribute('data-t'), S = null, range = 'y1', BASE_S = null, OWN = box.getAttribute('data-g') || 'base';
  var C = { m: '#f59e0b', r: '#3b82f6', grid: '#1f2a3a', txt: '#8b97a7', bg: '#0b0f17' };
  var RANGES = { m3: 92, m6: 183, y1: 366, all: 0 };
  var ts = function (d) { var p = d.split('-'); return Date.UTC(+p[0], +p[1] - 1, +p[2]); };

  function view() {
    var n = S.d.length, i0 = 0;
    if (RANGES[range]) {
      var cut = ts(S.d[n - 1]) - RANGES[range] * 86400000;
      while (i0 < n - 1 && ts(S.d[i0]) < cut) i0++;
    }
    return { i0: i0, n: n };
  }
  function draw() {
    var v = view(), W = Math.max(300, box.clientWidth - 8), H = W < 480 ? 250 : 300;
    var L = 34, R = 36, Tp = 10, B = 22, pw = W - L - R, ph = H - Tp - B;
    var xs = [], i;
    for (i = v.i0; i < v.n; i++) xs.push(ts(S.d[i]));
    var x0 = xs[0], x1 = xs[xs.length - 1], dx = Math.max(1, x1 - x0);
    var rmax = 5;
    for (i = v.i0; i < v.n; i++) if (S.r[i] > rmax) rmax = S.r[i];
    rmax = Math.ceil(rmax / 5) * 5;
    var X = function (t) { return L + (t - x0) / dx * pw; };
    var YM = function (m) { return Tp + (100 - m) / 100 * ph; };
    var YR = function (r) { return Tp + (r - 1) / (rmax - 1) * ph; };
    var g = '';
    [0, 25, 50, 75, 100].forEach(function (m) {
      g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + YM(m) + '" y2="' + YM(m) + '" stroke="' + C.grid + '" stroke-width="1"/>' +
        '<text x="' + (L - 5) + '" y="' + (YM(m) + 3.5) + '" fill="' + C.m + '" font-size="10" text-anchor="end">' + m + '</text>';
    });
    var rt = [1, Math.round(rmax / 4), Math.round(rmax / 2), Math.round(rmax * 3 / 4), rmax];
    rt.filter(function (x, k) { return rt.indexOf(x) === k; }).forEach(function (r) {
      g += '<text x="' + (W - R + 5) + '" y="' + (YR(r) + 3.5) + '" fill="' + C.r + '" font-size="10">' + r + '</text>';
    });
    var nt = W < 480 ? 3 : 6;
    for (var k = 0; k <= nt; k++) {
      var t = x0 + dx * k / nt, dd = new Date(t), lab = dd.getUTCFullYear() + '-' + ('0' + (dd.getUTCMonth() + 1)).slice(-2);
      g += '<text x="' + X(t) + '" y="' + (H - 6) + '" fill="' + C.txt + '" font-size="10" text-anchor="' + (k === 0 ? 'start' : (k === nt ? 'end' : 'middle')) + '">' + lab + '</text>';
    }
    function path(arr, Y) {
      var s = '', prev = null;
      for (var j = v.i0; j < v.n; j++) {
        var t2 = ts(S.d[j]);
        s += (prev === null || t2 - prev > 12 * 86400000 ? 'M' : 'L') + X(t2).toFixed(1) + ' ' + Y(arr[j]).toFixed(1);
        prev = t2;
      }
      return s;
    }
    var svg = '<svg id="csvg" viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + T + ' M-score와 순위 추이">' +
      '<rect x="0" y="0" width="' + W + '" height="' + H + '" fill="' + C.bg + '"/>' + g +
      '<path d="' + path(S.r, YR) + '" fill="none" stroke="' + C.r + '" stroke-width="1.5" stroke-linejoin="round"/>' +
      '<path d="' + path(S.m, YM) + '" fill="none" stroke="' + C.m + '" stroke-width="2" stroke-linejoin="round"/>' +
      '<line id="cx" x1="0" x2="0" y1="' + Tp + '" y2="' + (H - B) + '" stroke="#8b97a7" stroke-width="1" stroke-dasharray="3 3" visibility="hidden"/>' +
      '<circle id="cm" r="3.5" fill="' + C.m + '" stroke="#fff" stroke-width="1" visibility="hidden"/><circle id="cr" r="3.5" fill="' + C.r + '" stroke="#fff" stroke-width="1" visibility="hidden"/>' +
      '<rect id="chit" x="' + L + '" y="' + Tp + '" width="' + pw + '" height="' + ph + '" fill="transparent" style="touch-action:pan-y"/></svg>';
    box.innerHTML = svg;
    var cx = document.getElementById('cx'), cm = document.getElementById('cm'), cr = document.getElementById('cr');
    function at(idx, on) {
      if (idx < v.i0 || idx >= v.n) idx = v.n - 1;
      var xx = X(ts(S.d[idx]));
      cx.setAttribute('x1', xx); cx.setAttribute('x2', xx); cm.setAttribute('cx', xx); cm.setAttribute('cy', YM(S.m[idx])); cr.setAttribute('cx', xx); cr.setAttribute('cy', YR(S.r[idx]));
      var vis = on ? 'visible' : 'hidden';
      cx.setAttribute('visibility', vis); cm.setAttribute('visibility', vis); cr.setAttribute('visibility', vis);
      document.getElementById('creadout').innerHTML = '<b>' + S.d[idx] + '</b> · M-score <b style="color:' + C.m + '">' + S.m[idx].toFixed(1) + '</b> · 순위 <b style="color:' + C.r + '">' + S.r[idx] + '위</b> <span class="mu">/ ' + S.n[idx] + '종</span>';
    }
    function nearest(clientX) {
      var rc = document.getElementById('csvg').getBoundingClientRect(), t = x0 + ((clientX - rc.left) * (W / rc.width) - L) / pw * dx, lo = v.i0, hi = v.n - 1;
      while (lo < hi) { var mid = (lo + hi) >> 1; if (ts(S.d[mid]) < t) lo = mid + 1; else hi = mid; }
      if (lo > v.i0 && Math.abs(ts(S.d[lo - 1]) - t) < Math.abs(ts(S.d[lo]) - t)) lo--;
      return lo;
    }
    var hit = document.getElementById('chit');
    ['pointermove', 'pointerdown'].forEach(function (ev) { hit.addEventListener(ev, function (e) { at(nearest(e.clientX), true); }); });
    hit.addEventListener('pointerleave', function () { at(v.n - 1, false); });
    at(v.n - 1, false);
  }
  function setRange(r) {
    range = r;
    Array.prototype.forEach.call(document.querySelectorAll('[data-range]'), function (b) { b.classList.toggle('on', b.getAttribute('data-range') === r); });
    draw();
  }
  Array.prototype.forEach.call(document.querySelectorAll('[data-range]'), function (b) { b.addEventListener('click', function () { setRange(b.getAttribute('data-range')); }); });
  var rt;
  window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { if (S) draw(); }, 150); });
  fetch('../data/series/' + T + '.json').then(function (r) { if (!r.ok) throw 0; return r.json(); }).then(function (j) {
    S = j; if (!S.d.length) throw 0; BASE_S = j;
    var span = (ts(S.d[S.d.length - 1]) - ts(S.d[0])) / 86400000;
    setRange(span < 366 ? 'all' : 'y1');
    initPool();
  }).catch(function () { box.innerHTML = '<div class="chartnote">차트 데이터를 읽지 못했습니다(웹 주소로 여십시오).</div>'; });

  /* 풀(모집단) 선택 — 86개 종목 페이지 공통(MM-PRODUCT-POOL-CHARTS-20261124). 버튼 5개(미국 기본·크립토·채권·해외지수·인버스), 그 종목이 속한 그룹(data-g)은 켜진 채 고정(🔒).
     기본 상태: 미국 기본 종목 = 미국 기본만 / 신규 종목 = 5개 전부. 이 기본 상태의 M-score·순위·차트는 저장된 data/series/<티커>.json 그대로이고(현행과 같은 숫자),
     다른 조합이면 data/raw 원값에서 그룹 엔진(groups.js)이 켜진 그룹 모집단으로 다시 계산한다 — 상단 숫자·차트 두 선 모두.
     선택은 종목 페이지 공용으로 localStorage(mm_pool_v1)에 기억하되 자기 그룹 고정이 우선, 저장값이 없으면 기본 상태. */
  var STORE = 'mm_pool_v1', MG = null, DEF = [], tok = 0;
  function readSaved() { try { var a = JSON.parse(window.localStorage.getItem(STORE)); return Array.isArray(a) ? a : null; } catch (e) { return null; } }
  function writeSaved(a) { try { window.localStorage.setItem(STORE, JSON.stringify(a)); } catch (e) { /* 저장 불가 */ } }
  function sameSet(a, b) { return a.length === b.length && a.every(function (x) { return b.indexOf(x) >= 0; }); }
  function initPool() {
    var bar = document.querySelector('[data-gbar]'), ro = document.getElementById('creadout');
    if (!bar || !window.MMG) return;
    fetch('../data/groups_meta.json').then(function (r) { return r.json(); }).then(function (cfg) {
      MG = window.MMG.init(cfg, '../', { persist: false });
      var ids = cfg.groups.map(function (g) { return g.id; }).filter(function (id) { return MG.n[id] > 0; });
      DEF = OWN === 'base' ? ['base'] : ids.slice();
      var saved = readSaved(), init = saved ? saved.filter(function (id) { return ids.indexOf(id) >= 0; }) : DEF.slice();
      if (init.indexOf(OWN) < 0) init.push(OWN);                       // 자기 그룹 고정(저장값·기본값보다 우선)
      MG.sel = {}; init.forEach(function (id) { MG.sel[id] = true; });
      function render() { MG.renderBar(bar, { locked: [OWN], onChange: function (sel) { writeSaved(sel); apply(); } }); }
      render(); apply();
    }).catch(function () { bar.hidden = true; if (ro) ro.textContent = ''; });
  }
  function poolLabel(sel) { var L = {}; MG.cfg.groups.forEach(function (g) { L[g.id] = g.label; }); return sel.map(function (id) { return L[id]; }).join('·'); }
  function apply() {
    var sel = MG.selected(), my = ++tok, ro = document.getElementById('creadout'), st = document.getElementById('pstat'), nb = document.getElementById('pbasis');
    var isDef = sameSet(sel, DEF), tset = MG.tickers(sel), npool = Object.keys(tset).length;
    if (nb) nb.textContent = 'M-score·순위 기준: ' + poolLabel(sel) + ' 모집단(풀 ' + npool + '종, 날짜별로 순위에 든 종목만 집계)' + (isDef ? ' — 기본 상태' : ' — 원값에서 다시 계산');
    // 상단 숫자(최신 기준일): 연도 파일은 마지막 해 1개만 읽는다
    MG.loadIndex().then(function () {
      var last = MG.cal[MG.cal.length - 1]; return MG.ensure([last], 0).then(function () { return last; });
    }).then(function (last) {
      if (my !== tok) return;
      var sc = MG.dayScores(MG.dayRows(last) || {}, tset), me = null; sc.forEach(function (x) { if (x.t === T) me = x; });
      if (st) st.innerHTML = me ? '<span class="mu">' + last + ' 기준</span><span><span class="pl">M-score</span><b>' + me.M.toFixed(1) + '</b></span><span><span class="pl">순위</span><b>' + sc.length + '종 중 ' + me.rank + '위</b></span>' +
        '<span><span class="pl">변동성</span>' + Math.round(me.p[0] * 100) + '</span><span><span class="pl">상대강도</span>' + Math.round(me.p[1] * 100) + '</span><span><span class="pl">추세</span>' + Math.round(me.p[2] * 100) + '</span>'
        : '<span class="mu">' + last + ' 기준 — 이 종목은 선택한 풀의 순위 모집단에 없습니다(상장 직후·제외 등)</span>';
    }).catch(function () { if (st) st.textContent = '그룹 원값을 읽지 못했습니다(웹 주소로 여십시오).'; });
    // 차트: 기본 상태 = 저장 계열 그대로, 아니면 전 구간을 켜진 모집단으로 다시 계산
    if (isDef) { S = BASE_S; draw(); return; }
    if (ro) ro.textContent = '선택한 그룹의 원값을 불러오는 중…';
    MG.ensureAll().then(function () {
      if (my !== tok) return;
      var s = MG.series(T, tset); if (!s.d.length) throw 0; S = s; draw();
    }).catch(function () { if (my === tok && ro) ro.textContent = '그룹 원값을 읽지 못했거나 이 풀에는 이 종목의 순위 이력이 없습니다.'; });
  }
})();
