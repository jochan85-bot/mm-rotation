/* 종목 페이지 가격 차트 — 3배 상품 자체의 분할·병합 조정 일봉 캔들(주봉은 이 파일에서 일봉을 묶어 만든다). M-score 차트와 연동하지 않는 독립 차트.
   데이터: data/charts/<티커>.json = {t, v, d0, dt:[달력일 차], o, h, l, c} — 이 페이지를 열 때 그 종목 파일 1개만 읽는다.
   라이브러리: TradingView Lightweight Charts™ 5.2.1 (Apache-2.0, 버전 고정 CDN + SRI). 불러오지 못하면 차트 자리에 안내 문구만 나오고 페이지 나머지는 그대로다.
   상승·하락 색 = 사이트 공용 변수 --up(초록)·--dn(빨강). 판·글자·격자 색도 mm.css 변수를 읽는다(색 구성이 바뀌면 다시 적용).
   시세 오류 봉 표시 보정: #pchart 의 data-ov = [{d:날짜, f:'o'|'h'|'l'|'c', v?:값}](목록 data/chart_overrides.yaml). 그리기 직전 일봉에만 적용 — v 가 있으면 그 필드를
   v(두 번째 시세 소스의 정상값)로 바꾸고, 없으면 저가는 min(시가, 종가), 고가는 max(시가, 종가) 밖일 때 거기로 자른다(값 교체 먼저, 자르기 나중).
   주봉은 보정된 일봉으로 묶는다. 받은 데이터 파일은 그대로다.
   가격 표시(축 눈금·십자선·판독 줄 공통) = fmt(): 1 이상 소수 2자리(천 단위 쉼표), 1 미만 유효숫자 3자리. */
(function () {
  'use strict';
  var box = document.getElementById('pchart');
  if (!box) return;
  var T = box.getAttribute('data-t');
  var LIB = 'https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js';
  var SRI = 'sha384-KkYqTZlM13Zya6fVUF3IGCBOQ1ehFeJVVgxaVvD/0MebineF9EI8Jkd3NnWNChqN';
  var MONTHS = { m1: 1, m3: 3, m6: 6, y1: 12, y3: 36, all: 0 };
  var st = { iv: 'd', range: 'y1', log: false }, D = null, W = null, chart = null, series = null, LW = null;
  var out = document.getElementById('preadout');
  var OV = []; try { OV = JSON.parse(box.getAttribute('data-ov') || '[]'); } catch (e) { OV = []; }

  function fail() {
    box.innerHTML = '<div class="chartnote pfail">차트를 불러오지 못했습니다.</div>';
    if (out) out.textContent = '';
    Array.prototype.forEach.call(document.querySelectorAll('.pbar .btn'), function (b) { b.disabled = true; });
  }
  function loadLib() {
    return new Promise(function (ok, no) {
      if (window.LightweightCharts) return ok(window.LightweightCharts);
      var s = document.createElement('script'), done = false;
      s.src = LIB; s.integrity = SRI; s.crossOrigin = 'anonymous'; s.async = true;
      s.onload = function () { done = true; window.LightweightCharts ? ok(window.LightweightCharts) : no(); };
      s.onerror = function () { done = true; no(); };
      setTimeout(function () { if (!done) no(); }, 20000);
      document.head.appendChild(s);
    });
  }
  function bars(j) {                                    // 열 배열 → [{time(UTC 초), open, high, low, close}]
    var a = [], t = Date.UTC(+j.d0.slice(0, 4), +j.d0.slice(5, 7) - 1, +j.d0.slice(8, 10)) / 1000;
    for (var i = 0; i < j.c.length; i++) {
      t += j.dt[i] * 86400;
      a.push({ time: t, open: j.o[i], high: j.h[i], low: j.l[i], close: j.c[i] });
    }
    return a;
  }
  function ymdKey(t) { return new Date(t * 1000).toISOString().slice(0, 10); }
  function fix(a, ov) {                                 // 표시 보정 — 지정 봉의 값 교체(v) 또는 저가/고가를 시가·종가 범위로 자름(새 배열·새 봉, 원본 배열 불변)
    if (!ov || !ov.length) return a;
    var K = { o: 'open', h: 'high', l: 'low', c: 'close' };
    var m = {}; ov.forEach(function (x) { (m[x.d] = m[x.d] || []).push(x); });
    return a.map(function (b) {
      var fs = m[ymdKey(b.time)]; if (!fs) return b;
      var n = { time: b.time, open: b.open, high: b.high, low: b.low, close: b.close };
      fs.forEach(function (x) { if (typeof x.v === 'number' && K[x.f]) n[K[x.f]] = x.v; });
      fs.forEach(function (x) {
        if (typeof x.v === 'number') return;
        if (x.f === 'l' && n.low < Math.min(n.open, n.close)) n.low = Math.min(n.open, n.close);
        if (x.f === 'h' && n.high > Math.max(n.open, n.close)) n.high = Math.max(n.open, n.close);
      });
      return n;
    });
  }
  function weekly(a) {                                  // 주(월요일 시작) 단위 — 시가=첫 봉, 고가=최대, 저가=최소, 종가=마지막 봉. 휴장으로 빠진 날은 있는 봉만 묶는다
    var w = [], cur = null, key = null;
    a.forEach(function (b) {
      var dow = new Date(b.time * 1000).getUTCDay(), k = b.time - ((dow + 6) % 7) * 86400;
      if (k !== key) { if (cur) w.push(cur); key = k; cur = { time: b.time, open: b.open, high: b.high, low: b.low, close: b.close }; }
      else { if (b.high > cur.high) cur.high = b.high; if (b.low < cur.low) cur.low = b.low; cur.close = b.close; }
    });
    if (cur) w.push(cur);
    return w;
  }
  function css(n, d) { var v = getComputedStyle(document.documentElement).getPropertyValue(n).trim(); return v || d; }
  function theme() {
    return {
      layout: { background: { type: 'solid', color: css('--bg2', '#0b0f17') }, textColor: css('--muted', '#8b949e'), attributionLogo: true,
        fontFamily: getComputedStyle(document.body).fontFamily },
      grid: { vertLines: { color: css('--grid', '#1f2a3a') }, horzLines: { color: css('--grid', '#1f2a3a') } },
      rightPriceScale: { borderColor: css('--border', '#30363d'), entireTextOnly: true, scaleMargins: { top: 0.08, bottom: 0.16 } },   // 맨 위·아래 눈금 글자가 잘리면 숨김 / 아래 여백 = 왼쪽 아래 TradingView 로고(높이 19px, 바닥에서 10px) 자리 — 봉이 로고 밑으로 들어가지 않게
      timeScale: { borderColor: css('--border', '#30363d') }
    };
  }
  function colors() {
    var up = css('--up', '#22c55e'), dn = css('--dn', '#ef4444');
    return { upColor: up, downColor: dn, borderUpColor: up, borderDownColor: dn, wickUpColor: up, wickDownColor: dn };
  }
  function fmt(p) {                                     // 1 이상 = 소수 2자리(쉼표), 1 미만 = 유효숫자 3자리(지수 표기 없이)
    if (typeof p !== 'number' || !isFinite(p)) return '';
    var a = Math.abs(p);
    if (a >= 1 || a === 0) return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    var s = p.toPrecision(3);
    if (s.indexOf('e') >= 0) s = p.toFixed(Math.min(20, 2 - Math.floor(Math.log10(a))));
    return s;
  }
  function ymd(t) { var d = new Date(t * 1000); return d.getUTCFullYear() + '-' + ('0' + (d.getUTCMonth() + 1)).slice(-2) + '-' + ('0' + d.getUTCDate()).slice(-2); }
  function readout(b) {
    if (!out) return;
    if (!b) { out.textContent = ''; return; }
    var up = b.close >= b.open;
    out.innerHTML = '<b>' + ymd(b.time) + '</b>' + (st.iv === 'w' ? ' 주' : '') + ' · 시 ' + fmt(b.open) + ' · 고 ' + fmt(b.high) + ' · 저 ' + fmt(b.low) +
      ' · 종 <b class="' + (up ? 'up' : 'dn') + '">' + fmt(b.close) + '</b>';
  }
  function data() { return st.iv === 'w' ? W : D; }
  function sync() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-piv]'), function (b) { var on = b.getAttribute('data-piv') === st.iv; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-prange]'), function (b) { var on = b.getAttribute('data-prange') === st.range; b.classList.toggle('on', on); b.setAttribute('aria-pressed', on); });
    var lb = document.querySelector('[data-pscale]');
    if (lb) { lb.textContent = st.log ? '로그 축' : '선형 축'; lb.setAttribute('aria-pressed', st.log); lb.classList.toggle('on', st.log); }
  }
  function apply() {
    var a = data(); if (!a || !a.length) return;
    series.setData(a);
    chart.priceScale('right').applyOptions({ mode: st.log ? LW.PriceScaleMode.Logarithmic : LW.PriceScaleMode.Normal, autoScale: true });
    rng(); requestAnimationFrame(rng);                // 자동 크기(autoSize)가 폭을 확정한 뒤 한 번 더 — 먼저 맞추면 전체 보기의 오른쪽 끝이 잘린다
    readout(a[a.length - 1]); sync();
  }
  function rng() {
    var a = data(), last = a[a.length - 1].time, n = MONTHS[st.range];
    if (n) {
      var d = new Date(last * 1000); d.setUTCMonth(d.getUTCMonth() - n);
      chart.timeScale().setVisibleRange({ from: Math.max(a[0].time, d.getTime() / 1000), to: last });
    } else chart.timeScale().fitContent();
  }
  function init(lw, j) {
    LW = lw; D = fix(bars(j), OV); W = weekly(D);
    if (!D.length) return fail();
    box.innerHTML = '';
    var o = theme();
    o.autoSize = true;
    o.localization = { locale: 'ko-KR', dateFormat: 'yyyy-MM-dd', priceFormatter: fmt };
    o.handleScroll = { vertTouchDrag: false };
    o.crosshair = { mode: lw.CrosshairMode.Normal };
    o.timeScale.fixLeftEdge = true; o.timeScale.fixRightEdge = true; o.timeScale.minBarSpacing = 0.01;   // 전체(일봉 4천여 개)도 좁은 화면 폭에 다 들어가게
    chart = lw.createChart(box, o);
    series = chart.addSeries(lw.CandlestickSeries, Object.assign({ priceLineVisible: false, priceFormat: { type: 'price', precision: 3, minMove: 0.001 } }, colors()));   // 눈금 간격 하한 0.001(1 미만 가격용) — 글자는 fmt
    chart.subscribeCrosshairMove(function (p) {
      var b = p && p.time !== undefined && p.seriesData ? p.seriesData.get(series) : null;
      var a = data(); readout(b && b.open !== undefined ? b : a[a.length - 1]);
    });
    apply();
    var w0 = 0;
    chart.timeScale().subscribeSizeChange(function (w) { if (Math.abs(w - w0) > 1) { w0 = w; rng(); } });   // 화면 회전·창 크기 변경 때 선택한 기간을 다시 맞춘다
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)'), re = function () { chart.applyOptions(theme()); series.applyOptions(colors()); };
      if (mq.addEventListener) mq.addEventListener('change', re); else if (mq.addListener) mq.addListener(re);
    }
  }
  Array.prototype.forEach.call(document.querySelectorAll('[data-piv]'), function (b) {
    b.addEventListener('click', function () { st.iv = b.getAttribute('data-piv'); if (chart) apply(); else sync(); });
  });
  Array.prototype.forEach.call(document.querySelectorAll('[data-prange]'), function (b) {
    b.addEventListener('click', function () { st.range = b.getAttribute('data-prange'); st.log = st.range === 'all'; if (chart) apply(); else sync(); });
  });
  var sb = document.querySelector('[data-pscale]');
  if (sb) sb.addEventListener('click', function () {                 // 축만 바꾼다(보고 있는 구간은 유지)
    st.log = !st.log; sync();
    if (chart) chart.priceScale('right').applyOptions({ mode: st.log ? LW.PriceScaleMode.Logarithmic : LW.PriceScaleMode.Normal, autoScale: true });
  });
  sync();
  var pj = fetch('../data/charts/' + T + '.json').then(function (r) { if (!r.ok) throw 0; return r.json(); });
  Promise.all([loadLib(), pj]).then(function (x) { init(x[0], x[1]); }).catch(fail);
})();
