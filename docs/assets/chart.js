/* 종목 페이지 M-score·순위 추이 차트 — 선 2개(M-score 좌축, 순위 우축·역순), 기간 버튼 3개월·6개월·1년·전체.
   크립토/골드 시그널 리포트 차트 서식(어두운 판 #0b0f17, 격자 #1f2a3a, 앰버·블루 이중 축)을 따르되 외부 라이브러리 없이 SVG 로 그린다.
   데이터: data/series/<티커>.json = {t, d:[날짜], m:[M-score], r:[순위], n:[그날 모집단 수]} (일일 산출 말미에 scores CSV 에서 생성). */
(function () {
  'use strict';
  var box = document.getElementById('chart');
  if (!box) return;
  var T = box.getAttribute('data-t'), S = null, range = 'y1';
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
    S = j; if (!S.d.length) throw 0;
    var span = (ts(S.d[S.d.length - 1]) - ts(S.d[0])) / 86400000;
    setRange(span < 366 ? 'all' : 'y1');
  }).catch(function () { box.innerHTML = '<div class="chartnote">차트 데이터를 읽지 못했습니다(웹 주소로 여십시오).</div>'; });
})();
