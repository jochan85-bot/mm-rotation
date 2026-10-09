/* 메인 순위표 — 달력 선택(같은 자리에서 표 교체)·요약/상세 전환·행 펼침·주의 아이콘. 외부 라이브러리 0.
   데이터: 최신 기준일은 페이지에 내장(#mmdata), 다른 날짜는 data/scores/<날짜>.csv 를 읽는다. 렌더 스크립트: scripts/mm_site.py */
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('mmdata').textContent);
  var $ = function (i) { return document.getElementById(i); };
  var st = { date: D.asof, mode: 'sum', y: 0, m: 0, calOpen: true, cache: {}, rows: null, token: 0 };
  var avail = {};
  D.dates.forEach(function (d) { avail[d] = 1; });

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function num(v) { if (v === '' || v === undefined || v === null) return null; var x = parseFloat(v); return isNaN(x) ? null : x; }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function fx(x, n, sg) {
    if (x === null || x === undefined || isNaN(x)) return '—';
    var s = Math.abs(x).toLocaleString('en-US', { minimumFractionDigits: n, maximumFractionDigits: n });
    return (x < 0 && s.replace(/[0.,]/g, '') !== '' ? '−' : (sg ? '+' : '')) + s;
  }
  function pct(p) { return p === null ? '—' : String(Math.round(p * 100)); }

  var NUMS = ['rank', 'M', 'sig', 'p_sig', 'rsA', 'p_rsA', 'f1b', 'p_f1b', 'c1_ma200', 'above200', 'close3', 'adtv', 'listed_days', 'beta', 'r2', 'n_beta'];
  function norm(o) {
    var r = {};
    for (var k in o) r[k] = o[k];
    NUMS.forEach(function (k) { r[k] = num(o[k]); });
    r.ticker = String(o.ticker); r.badges = o.badges ? String(o.badges) : ''; r.proxy = String(o.proxy || '');
    r.d_rank = (o.d_rank === undefined || o.d_rank === null) ? '' : String(o.d_rank);
    return r;
  }
  function parseCsv(t) {
    var L = t.split('\n'), cols = L[1].split(','), rows = [];
    for (var i = 2; i < L.length; i++) {
      if (!L[i]) continue;
      var c = L[i].split(','), o = {};
      cols.forEach(function (k, j) { o[k] = c[j]; });
      rows.push(norm(o));
    }
    return rows;
  }

  /* ---- 주의 사유: 신규·저유동·무거래·표본부족 4종만(근사 배지는 아이콘 대상 아님) ---- */
  function why(r) {
    var o = [], b = r.badges ? r.badges.split(' · ') : [];
    b.forEach(function (x) {
      if (x === '신규') o.push('신규 ' + r.listed_days + '일');
      else if (x === '저유동') o.push('거래대금 $' + fx(r.adtv, 2) + 'M');
      else if (x.indexOf('무거래') === 0) o.push('무거래 ' + x.slice(3) + '일');
      else if (x === '표본부족') o.push('표본 ' + r.n_beta + '개');
    });
    return o;
  }
  function groups(rows) {
    var by = {}, out = [], seen = {};
    rows.forEach(function (r) { (by[r.proxy] = by[r.proxy] || []).push(r); });
    rows.forEach(function (r) {
      var g = by[r.proxy];
      if (g.length < 2) out.push({ rep: r, mem: [r], grp: false });
      else if (!seen[r.proxy]) {
        seen[r.proxy] = 1;
        var m = g.slice().sort(function (a, b) { return b.adtv - a.adtv; });
        out.push({ rep: m[0], mem: m, grp: true });
      }
    });
    return out;
  }
  function whyText(g) {
    if (!g.grp) return why(g.rep).join(' · ');
    var a = [];
    g.mem.forEach(function (m) { var w = why(m); if (w.length) a.push(m.ticker + ': ' + w.join(' · ')); });
    return a.join(' / ');
  }
  function drank(v) {
    if (v === '') return '—';
    if (v === '신규') return '신규';
    var x = parseInt(v, 10);
    if (isNaN(x)) return esc(v);
    return x > 0 ? '<span class="up">▲' + x + '</span>' : (x < 0 ? '<span class="dn">▼' + (-x) + '</span>' : '0');
  }
  function tkLink(t) { return '<a href="products/' + esc(t) + '.html">' + esc(t) + '</a>'; }
  function ixName(t) { var m = D.tk[t]; return m ? m.ix : ''; }

  var EXTRA = [
    ['σ60 (%)', function (g) { return fx(g.rep.sig * 100, 1); }],
    ['12개월 수익률 (%)', function (g) { return fx(g.rep.rsA * 100, 1, true); }],
    ['MA50/MA200−1 (%)', function (g) { return fx(g.rep.f1b * 100, 2, true); }],
    ['1x 종가/MA200−1 (%)', function (g) { return fx(g.rep.c1_ma200 * 100, 1, true); }],
    ['200일선 상회', function (g) { return g.rep.above200 === 1 ? '○' : '×'; }],
    ['3배 종가', function (g) { return fx(g.rep.close3, 2); }, 1],
    ['20일 거래대금 ($M)', function (g) { return fx(g.rep.adtv, 1); }, 1],
    ['상장 거래일수', function (g) { return fx(g.rep.listed_days, 0); }, 1],
    ['Δ순위 (5일)', function (g) { return drank(g.rep.d_rank); }],
    ['동일 지수 그룹', function (g) { return g.grp ? esc(ixName(g.rep.ticker)) + ' ×' + g.mem.length : '—'; }]
  ];

  function kvPanel(g) {
    var h = '<div class="kv">';
    EXTRA.forEach(function (e) { h += '<div><span class="k">' + e[0] + '</span><span class="v">' + e[1](g) + '</span></div>'; });
    h += '</div>';
    return h;
  }
  function memTable(g) {
    var h = '<table class="mem"><thead><tr><th class="l">티커</th><th class="l">발행사</th><th>3배 종가</th><th>거래대금($M)</th><th>상장일수</th><th class="l">주의</th></tr></thead><tbody>';
    g.mem.forEach(function (m) {
      var meta = D.tk[m.ticker] || { iss: '', typ: '' }, w = why(m);
      h += '<tr><td class="l">' + tkLink(m.ticker) + '</td><td class="l">' + esc(meta.iss + ' · ' + meta.typ) + '</td><td>' + fx(m.close3, 2) + '</td><td>' + fx(m.adtv, 1) + '</td><td>' + fx(m.listed_days, 0) + '</td><td class="l">' + (w.length ? '<span class="wh" data-w="' + esc(w.join(' · ')) + '">!</span> ' + esc(w.join(' · ')) : '—') + '</td></tr>';
    });
    return h + '</tbody></table>';
  }

  var TIPS = {
    M: '변동성·상대강도·추세 세 점수의 평균 (유니버스 내 상대 점수, 100=최상위)',
    V: '유니버스 내 상대 점수, 100=최상위 — 1x 지수의 최근 60일 변동성(σ60) 백분위',
    R: '유니버스 내 상대 점수, 100=최상위 — 1x 지수의 12개월 수익률(최근 1개월 제외) 백분위',
    T: '유니버스 내 상대 점수, 100=최상위 — 1x 지수의 MA50/MA200−1 백분위'
  };
  function head() {
    var h = '<tr><th class="c">순위</th><th class="l">티커</th>' +
      '<th class="tip" data-w="' + esc(TIPS.M) + '" title="' + esc(TIPS.M) + '">M-score</th>' +
      '<th class="tip" data-w="' + esc(TIPS.V) + '" title="' + esc(TIPS.V) + '">변동성</th>' +
      '<th class="tip" data-w="' + esc(TIPS.R) + '" title="' + esc(TIPS.R) + '">상대강도</th>' +
      '<th class="tip" data-w="' + esc(TIPS.T) + '" title="' + esc(TIPS.T) + '">추세</th><th class="l">!</th>';
    if (st.mode === 'det') EXTRA.forEach(function (e) { h += '<th>' + e[0] + '</th>'; });
    return h + '</tr>';
  }
  function body(rows) {
    var gs = groups(rows), h = '', ncol = 7 + (st.mode === 'det' ? EXTRA.length : 0);
    gs.forEach(function (g, i) {
      var r = g.rep, wt = whyText(g);
      var tk = g.grp ? '<span class="car">▸</span>' + esc(r.ticker) + '<span class="more">+' + (g.mem.length - 1) + '</span>' : tkLink(r.ticker);
      h += '<tr class="r" data-i="' + i + '"><td class="rk1">' + fx(r.rank, 0) + '</td><td class="tk">' + tk + '</td><td class="m">' + fx(r.M, 1) +
        '</td><td class="sc">' + pct(r.p_sig) + '</td><td class="sc">' + pct(r.p_rsA) + '</td><td class="sc">' + pct(r.p_f1b) + '</td>' +
        '<td class="wc">' + (wt ? '<span class="wh" data-w="' + esc(wt) + '">!</span><span class="wt">' + esc(wt) + '</span>' : '') + '</td>';
      if (st.mode === 'det') EXTRA.forEach(function (e) { h += '<td' + (g.grp && e[2] ? ' class="mu" title="대표(거래대금 최대) 종목 ' + esc(r.ticker) + ' 값 — 펼치면 개별 값"' : '') + '>' + e[1](g) + '</td>'; });
      h += '</tr>';
      var panel = (st.mode === 'sum' ? kvPanel(g) : '') + (g.grp ? memTable(g) : '');
      if (panel) h += '<tr class="dt" hidden><td colspan="' + ncol + '"><div class="panel">' + panel + '</div></td></tr>';
    });
    return h;
  }
  function renderTable() {
    var rows = st.rows, t = $('rk');
    $('ttl').innerHTML = '<b>' + st.date + ' 기준</b> <span>· ' + rows.length + '종' + (st.date === D.asof ? ' · 최신' : '') + '</span>';
    $('todaybtn').hidden = (st.date === D.asof);
    $('modebtn').textContent = st.mode === 'sum' ? '상세보기' : '요약보기';
    $('modebtn').classList.toggle('on', st.mode === 'det');
    t.innerHTML = '<thead>' + head() + '</thead><tbody>' + body(rows) + '</tbody>';
  }

  /* ---- 날짜 로드 ---- */
  function load(d) {
    var tok = ++st.token;
    if (d === D.asof) { st.rows = D.latest.map(norm); st.date = d; renderTable(); return; }
    if (st.cache[d]) { st.rows = st.cache[d]; st.date = d; renderTable(); return; }
    $('ttl').innerHTML = '<b>' + d + ' 기준</b> <span>· 불러오는 중…</span>';
    fetch('data/scores/' + d + '.csv').then(function (r) { if (!r.ok) throw 0; return r.text(); }).then(function (t) {
      if (tok !== st.token) return;
      st.cache[d] = parseCsv(t); st.rows = st.cache[d]; st.date = d; renderTable();
    }).catch(function () {
      if (tok !== st.token) return;
      $('ttl').innerHTML = '<b>' + d + ' 기준</b> <span>· 이 날짜 파일을 읽지 못했습니다(웹 주소로 여십시오)</span>';
    });
  }
  function select(d) {
    if (!avail[d]) return;
    var p = d.split('-'); st.y = +p[0]; st.m = +p[1];
    load(d); drawCal();
    try { history.replaceState(null, '', d === D.asof ? location.pathname : '#' + d); } catch (e) { /* file:// 등 */ }
  }

  /* ---- 달력 ---- */
  function drawCal() {
    var y = st.y, m = st.m, first = new Date(y, m - 1, 1).getDay(), last = new Date(y, m, 0).getDate();
    var h = '<div class="calbar"><span><button class="btn" id="cprev" aria-label="이전 달">‹</button> <b>' + y + '년 ' + m + '월</b> <button class="btn" id="cnext" aria-label="다음 달">›</button></span>' +
      '<button class="btn" id="ctog">' + (st.calOpen ? '접기 ▴' : '달력 ▾') + '</button></div>';
    if (st.calOpen) {
      h += '<div class="cal">' + ['일', '월', '화', '수', '목', '금', '토'].map(function (x) { return '<div class="wd">' + x + '</div>'; }).join('');
      for (var i = 0; i < first; i++) h += '<div></div>';
      for (var d = 1; d <= last; d++) {
        var k = y + '-' + pad(m) + '-' + pad(d);
        h += avail[k] ? '<button class="d' + (k === st.date ? ' sel' : '') + (k === D.asof ? ' last' : '') + '" data-d="' + k + '">' + d + '</button>' : '<div class="d">' + d + '</div>';
      }
      h += '</div>';
    }
    $('calbox').innerHTML = h;
  }
  function mv(dm) {
    var y = st.y, m = st.m + dm;
    if (m < 1) { m = 12; y--; } if (m > 12) { m = 1; y++; }
    var f = D.first.split('-'), l = D.last.split('-');
    if (y * 12 + m < (+f[0]) * 12 + (+f[1]) || y * 12 + m > (+l[0]) * 12 + (+l[1])) return;
    st.y = y; st.m = m; drawCal();
  }

  /* ---- 팝오버(주의 아이콘·열 머리 설명) ---- */
  var pop = $('pop');
  function showPop(el) {
    pop.textContent = el.getAttribute('data-w'); pop.hidden = false;
    var r = el.getBoundingClientRect(), w = pop.offsetWidth;
    pop.style.top = (r.bottom + 6) + 'px';
    pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + 'px';
    pop._src = el;
  }
  document.addEventListener('click', function (e) {
    var w = e.target.closest ? e.target.closest('[data-w]') : null;
    if (w) {
      e.stopPropagation();
      if (!pop.hidden && pop._src === w) { pop.hidden = true; return; }
      showPop(w); return;
    }
    pop.hidden = true;
    var b = e.target.closest ? e.target.closest('button,a') : null;
    var tr = e.target.closest ? e.target.closest('tr.r') : null;
    if (tr && !(b && b !== tr)) {
      var nx = tr.nextElementSibling;
      if (nx && nx.classList.contains('dt')) {
        nx.hidden = !nx.hidden; tr.classList.toggle('open', !nx.hidden);
        var c = tr.querySelector('.car'); if (c) c.textContent = nx.hidden ? '▸' : '▾';
      }
    }
  });
  window.addEventListener('scroll', function () { pop.hidden = true; }, true);

  $('modebtn').addEventListener('click', function () { st.mode = st.mode === 'sum' ? 'det' : 'sum'; renderTable(); });
  $('todaybtn').addEventListener('click', function () { select(D.asof); });
  $('calbox').addEventListener('click', function (e) {
    var t = e.target;
    if (t.id === 'cprev') mv(-1); else if (t.id === 'cnext') mv(1);
    else if (t.id === 'ctog') { st.calOpen = !st.calOpen; drawCal(); }
    else if (t.getAttribute && t.getAttribute('data-d')) select(t.getAttribute('data-d'));
  });

  var h0 = (location.hash || '').slice(1);
  var start = avail[h0] ? h0 : D.asof, p0 = start.split('-');
  st.y = +p0[0]; st.m = +p0[1];
  if (/[?&]cal=0/.test(location.search)) st.calOpen = false;
  if (/[?&]mode=det/.test(location.search)) st.mode = 'det';
  drawCal(); load(start);
})();
