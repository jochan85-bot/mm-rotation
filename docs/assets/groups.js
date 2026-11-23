/* 그룹 선택·점수 재계산 엔진 (MM-UNIVERSE-GROUPS-20261123). 외부 라이브러리 0.
   원값: data/raw/<연도>.json = {y, f:[필드], d:[날짜], t:{티커:[날짜 정렬 배열: [sig,rsA,f1b,pop,c1_ma200,above200,close3,adtv,listed_days,badges,beta,r2,n_beta] | null]}}, 달력: data/raw/index.json = {cal:[날짜], years:[연도]}
   알고리즘(파이썬 기준 구현 scripts/mm_groups.py 의 day_scores·series_scores 와 같다 — 시험이 둘을 대조):
     모집단 = 켜진 그룹의 종목 ∧ pop==1 ∧ 원값 3개(σ60·12-1개월 수익률·MA50/MA200−1) 있음.
     각 원값의 백분위 = (평균순위−1)/(N−1)  (동점은 평균순위, N=1 이면 0.5) — 변동성·상대강도·추세 3항,  M = (p1+p2+p3)/3×100,
     순위 = M 을 소수 6자리로 반올림한 값의 내림차순 1+(더 큰 값의 수) (동점은 같은 순위),  Δ순위 = 5거래일 전 순위 − 오늘 순위(5거래일 전 모집단에 없으면 '신규'). */
(function (root) {
  'use strict';
  var KEY = 'mm_groups_v1';
  var G = { cfg: null, sel: {}, base: '', years: {}, cal: [], idx: {}, hooks: [], fetchJson: null };
  var F = { sig: 0, rsA: 1, f1b: 2, pop: 3, c1_ma200: 4, above200: 5, close3: 6, adtv: 7, listed_days: 8, badges: 9, beta: 10, r2: 11, n_beta: 12 };
  G.F = F;

  /* ---------- 선택 상태(localStorage, 실패해도 조용히) ---------- */
  function readSaved() {
    try { var s = root.localStorage && root.localStorage.getItem(KEY); if (!s) return null; var a = JSON.parse(s); return Array.isArray(a) ? a : null; } catch (e) { return null; }
  }
  function save() {
    try { if (root.localStorage) root.localStorage.setItem(KEY, JSON.stringify(G.selected())); } catch (e) { /* 저장 불가(사생활 모드 등) */ }
  }
  G.init = function (cfg, base) {
    G.cfg = cfg; G.base = base || ''; G.sel = {};
    var n = {}; cfg.groups.forEach(function (g) { n[g.id] = 0; });
    Object.keys(cfg.gt).forEach(function (t) { n[cfg.gt[t]] = (n[cfg.gt[t]] || 0) + 1; });
    G.n = n;
    var saved = readSaved(), ok = {}; cfg.groups.forEach(function (g) { ok[g.id] = n[g.id] > 0; });
    if (saved) saved.forEach(function (id) { if (ok[id]) G.sel[id] = true; });
    else cfg.groups.forEach(function (g) { if (g['default'] && ok[g.id]) G.sel[g.id] = true; });
    return G;
  };
  G.selected = function () { return G.cfg.groups.map(function (g) { return g.id; }).filter(function (id) { return G.sel[id]; }); };
  G.isOn = function (id) { return !!G.sel[id]; };
  G.setOn = function (id, on) { if (!(G.n[id] > 0)) return; if (on) G.sel[id] = true; else delete G.sel[id]; save(); };
  G.isBaseOnly = function () { var s = G.selected(); return s.length === 1 && s[0] === 'base'; };
  G.tickers = function (ids) {
    var on = {}; (ids || G.selected()).forEach(function (i) { on[i] = 1; });
    var out = {}; Object.keys(G.cfg.gt).forEach(function (t) { if (on[G.cfg.gt[t]]) out[t] = 1; });
    return out;
  };

  /* ---------- 원값 로드 ---------- */
  function getJson(url) {
    if (G.fetchJson) return G.fetchJson(url);
    return root.fetch(url).then(function (r) { if (!r.ok) throw new Error(url + ' ' + r.status); return r.json(); });
  }
  G.loadIndex = function () {
    if (G.cal.length) return Promise.resolve();
    return getJson(G.base + 'data/raw/index.json').then(function (o) {
      G.cal = o.cal; G.idx = {}; o.cal.forEach(function (d, i) { G.idx[d] = i; }); G.allYears = o.years;
    });
  };
  var YV = {};                                                   // 연도 → 로드 완료된 객체(동기 접근용)
  function loadYear(y) {
    if (G.years[y]) return G.years[y];
    G.years[y] = getJson(G.base + 'data/raw/' + y + '.json').then(function (o) {
      var pos = {}; o.d.forEach(function (d, i) { pos[d] = i; }); o.pos = pos; YV[y] = o; return o;
    });
    return G.years[y];
  }
  /* 날짜 배열(과 그 직전 back 거래일)에 필요한 연도 파일을 로드 */
  G.ensure = function (dates, back) {
    return G.loadIndex().then(function () {
      var need = {};
      dates.forEach(function (d) {
        var i = G.idx[d]; if (i === undefined) return;
        var j = Math.max(0, i - (back === undefined ? 5 : back));
        need[+d.slice(0, 4)] = 1; need[+G.cal[j].slice(0, 4)] = 1;
      });
      return Promise.all(Object.keys(need).map(function (y) { return loadYear(+y); }));
    });
  };
  G.ensureAll = function () {
    return G.loadIndex().then(function () { return Promise.all(G.allYears.map(loadYear)); });
  };
  function yearObj(y) { return YV[y]; }
  G.dayRows = function (d) {
    var y = +d.slice(0, 4), o = yearObj(y); if (!o) return null;
    var p = o.pos[d]; if (p === undefined) return null;
    var out = {}; for (var t in o.t) { var r = o.t[t][p]; if (r) out[t] = r; }
    return out;
  };

  /* ---------- 점수 ---------- */
  function avgRankPct(vals) {
    var n = vals.length, ord = vals.map(function (v, i) { return i; }).sort(function (a, b) { return vals[a] - vals[b]; });
    var p = new Array(n), i = 0;
    if (n === 1) return [0.5];
    while (i < n) {
      var j = i; while (j + 1 < n && vals[ord[j + 1]] === vals[ord[i]]) j++;
      var avg = (i + j) / 2 + 1;                                  // 1-기준 평균순위
      for (var k = i; k <= j; k++) p[ord[k]] = (avg - 1) / (n - 1);
      i = j + 1;
    }
    return p;
  }
  function r6(x) { return Math.round(x * 1e6) / 1e6; }
  /* rows: {티커: 원값 행}, tset: {티커:1} → [{t,p:[3],M,rank}] (M 내림차순 정렬 아님 — 티커 알파벳순, 파이썬과 동일) */
  G.dayScores = function (rows, tset) {
    var t = Object.keys(tset).filter(function (k) { var r = rows[k]; return r && r[3] === 1 && r[0] !== null && r[1] !== null && r[2] !== null; }).sort();
    if (!t.length) return [];
    var cols = [0, 1, 2].map(function (j) { return avgRankPct(t.map(function (k) { return rows[k][j]; })); });
    var out = t.map(function (k, i) { var p = [cols[0][i], cols[1][i], cols[2][i]]; return { t: k, p: p, M: (p[0] + p[1] + p[2]) / 3 * 100 }; });
    out.forEach(function (x) { x.m6 = r6(x.M); });
    out.forEach(function (x) { var c = 0; out.forEach(function (y) { if (y.m6 > x.m6) c++; }); x.rank = 1 + c; });
    return out;
  };
  /* 기준일 d 의 표 행(표시용 객체) — 켜진 그룹 모집단으로 재계산. 반환 [{ticker,rank,M,p_sig,p_rsA,p_f1b,d_rank,sig,rsA,f1b,c1_ma200,above200,close3,adtv,listed_days,badges,beta,r2,n_beta}] (순위순) */
  G.table = function (d, tset) {
    var rows = G.dayRows(d); if (!rows) return null;
    var sc = G.dayScores(rows, tset), i = G.idx[d], prev = null;
    if (i >= 5) { var pr = G.dayRows(G.cal[i - 5]); prev = pr ? G.dayScores(pr, tset) : null; }
    var pm = {}; if (prev) prev.forEach(function (x) { pm[x.t] = x.rank; });
    var out = sc.map(function (x) {
      var r = rows[x.t], dr = (!prev || pm[x.t] === undefined) ? '신규' : String(pm[x.t] - x.rank);
      return { ticker: x.t, rank: x.rank, M: x.M, p_sig: x.p[0], p_rsA: x.p[1], p_f1b: x.p[2], d_rank: dr, sig: r[0], rsA: r[1], f1b: r[2], c1_ma200: r[4], above200: r[5],
        close3: r[6], adtv: r[7], listed_days: r[8], badges: r[9] || '', beta: r[10], r2: r[11], n_beta: r[12], proxy: '' };
    });
    out.sort(function (a, b) { return a.rank - b.rank || (a.ticker < b.ticker ? -1 : 1); });
    return out;
  };

  /* ---------- 종목별 M-score·순위 추이(차트용) — 달력 전 구간, 켜진 모집단 안에서 ---------- */
  G.series = function (ticker, tset, from) {
    var d = [], m = [], r = [], n = [];
    for (var i = 0; i < G.cal.length; i++) {
      var day = G.cal[i]; if (from && day < from) continue;
      var rows = G.dayRows(day); if (!rows) continue;
      var sc = G.dayScores(rows, tset), me = null;
      for (var k = 0; k < sc.length; k++) if (sc[k].t === ticker) { me = sc[k]; break; }
      if (me) { d.push(day); m.push(Math.round(me.M * 10) / 10); r.push(me.rank); n.push(sc.length); }
    }
    return { t: ticker, d: d, m: m, r: r, n: n };
  };

  /* ---------- 장기순위: N거래일 평균 M-score(창의 80% 미만이면 결측)를 오늘 모집단 안에서 순위. mm_site.compute_longterm 와 같은 규칙 ---------- */
  G.longterm = function (asof, tset, tabs) {
    var i1 = G.idx[asof], cache = {};
    function day(d) { if (!cache[d]) { var rows = G.dayRows(d); cache[d] = rows ? G.dayScores(rows, tset) : []; } return cache[d]; }
    var pop = day(asof).map(function (x) { return x.t; });
    return tabs.map(function (tb) {
      var N = tb[0], acc = {}; pop.forEach(function (t) { acc[t] = []; });
      for (var i = Math.max(0, i1 - N + 1); i <= i1; i++) day(G.cal[i]).forEach(function (x) { if (acc[x.t]) acc[x.t].push([x.M, x.p[0] * 100, x.p[1] * 100, x.p[2] * 100]); });
      var need = Math.ceil(0.8 * N), rows = pop.map(function (t) {
        var v = acc[t];
        if (v.length >= need) {
          var s = [0, 0, 0, 0]; v.forEach(function (a) { for (var k = 0; k < 4; k++) s[k] += a[k]; });
          var a = s.map(function (x) { return x / v.length; });
          return { t: t, m: r6(a[0]), v: Math.round(a[1]), rs: Math.round(a[2]), tr: Math.round(a[3]), n: v.length };
        }
        return { t: t, m: null, v: null, rs: null, tr: null, n: v.length };
      });
      var ok = rows.filter(function (x) { return x.m !== null; });
      rows.forEach(function (x) { x.r = null; if (x.m !== null) { var c = 0; ok.forEach(function (y) { if (y.m > x.m) c++; }); x.r = 1 + c; } });
      rows.sort(function (a, b) { var ra = a.r === null ? 1e9 : a.r, rb = b.r === null ? 1e9 : b.r; return ra - rb || (a.t < b.t ? -1 : 1); });
      return { k: N, rows: rows };
    });
  };

  /* ---------- 그룹 버튼 막대 ---------- */
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  /* el 안에 버튼을 그린다. opts.ids: 표시할 그룹 id(기본 전부), opts.onChange(selectedIds) */
  G.renderBar = function (el, opts) {
    opts = opts || {};
    var ids = opts.ids || G.cfg.groups.map(function (g) { return g.id; });
    var h = '';
    G.cfg.groups.forEach(function (g) {
      if (ids.indexOf(g.id) < 0) return;
      var empty = !(G.n[g.id] > 0), on = G.isOn(g.id) && !empty;
      h += '<button type="button" class="btn gb' + (on ? ' on' : '') + (empty ? ' off' : '') + '" data-g="' + esc(g.id) + '" aria-pressed="' + (on ? 'true' : 'false') + '"' + (empty ? ' disabled' : '') + '>' +
        esc(g.label) + (empty ? '<span class="soon">준비 중</span>' : '') + '</button>';
    });
    el.innerHTML = h;
    el.onclick = function (e) {
      var b = e.target.closest ? e.target.closest('button[data-g]') : null;
      if (!b || b.disabled) return;
      var id = b.getAttribute('data-g'); G.setOn(id, !G.isOn(id));
      G.renderBar(el, opts); if (opts.onChange) opts.onChange(G.selected());
    };
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = G; else root.MMG = G;
})(typeof window !== 'undefined' ? window : globalThis);
