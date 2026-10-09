/* 메인 순위표 — 달력 선택(같은 자리에서 표 교체)·요약/상세 전환·행 펼침·주의 아이콘. 외부 라이브러리 0.
   데이터: 최신 기준일은 페이지에 내장(#mmdata), 다른 날짜는 data/scores/<날짜>.csv 를 읽는다. 렌더 스크립트: scripts/mm_site.py */
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('mmdata').textContent);
  var $ = function (i) { return document.getElementById(i); };
  var st = { date: D.asof, mode: 'sum', y: 0, m: 0, calOpen: true, cache: {}, rows: null, token: 0, sort: { k: 'rank', dir: 1 } };
  var availYM = {};
  
  var avail = {};
  D.dates.forEach(function (d) { avail[d] = 1; availYM[+d.slice(0, 4) * 100 + +d.slice(5, 7)] = 1; });

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
  /* ◐ 되계산 경고(MM-RECON-RULE-REV-20261011): 선택한 날짜 포함 최근 252거래일 중 공식 지수 첫 날짜 이전(구성종목 복제 연장)에 속한 날의 비율. 표시 전용 — 점수·순위 불변 */
  var hcache = {};
  function rcInfo(t, d) {
    var c = D.rc && D.rc[t]; if (!c) return null;
    var k = t + '|' + d; if (k in hcache) return hcache[k];
    var i = D.dates.indexOf(d), W = D.histWin || 252, p = 0;
    if (i >= 0) {
      var a = Math.max(0, i + 1 - W), n = 0;
      for (var j = a; j <= i; j++) if (D.dates[j] < c.of) n++;
      p = n ? Math.max(1, Math.round(100 * n / (i + 1 - a))) : 0;
    }
    return (hcache[k] = p ? { p: p, of: c.of, rel: c.rel } : null);
  }
  function rcIcon(t) {
    var r = rcInfo(t, st.date); if (!r) return '';
    return '<span class="rc" data-w="' + esc('되계산 비중 ' + r.p + '% · 공식 지수 ' + r.of + '부터 · 해제 예정 ' + r.rel) + '">◐</span>';
  }
  function why(r) {
    var o = [], b = r.badges ? r.badges.split(' · ') : [];
    b.forEach(function (x) {
      if (x === '신규') o.push('신규 ' + r.listed_days + '일');
      else if (x === '저유동') o.push('$' + fx(r.adtv, 2) + 'M');
      else if (x.indexOf('무거래') === 0) o.push('무거래 ' + x.slice(3) + '일');
      else if (x === '표본부족') o.push('표본 ' + r.n_beta);
    });
    var rc = rcInfo(r.ticker, st.date);
    if (rc) o.push('재구성 ' + rc.p + '%');
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
  function whyLines(g) {
    if (!g.grp) return why(g.rep).join('<br>');
    var a = [];
    g.mem.forEach(function (m) { var w = why(m); if (w.length) a.push(esc(m.ticker) + ': ' + w.map(esc).join(' · ')); });
    return a.join('<br>');
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
    EXTRA.forEach(function (e) { if (g.grp && e[2]) return; h += '<div><span class="k">' + e[0] + '</span><span class="v">' + e[1](g) + '</span></div>'; });
    h += '</div>';
    return h;
  }
  /* 그룹 펼침: 멤버를 본 표와 같은 행(같은 열·글자·행 높이)으로 그린다. 멤버별 3배 종가·거래대금·상장일수·발행사는 패널의 작은 글씨 줄로 옮겼다. */
  function memInfo(g) {
    var h = '<div class="minfo">';
    g.mem.forEach(function (m) {
      var meta = D.tk[m.ticker] || { iss: '', typ: '' };
      h += '<div><b>' + esc(m.ticker) + '</b> ' + esc(meta.iss + ' · ' + meta.typ) + ' · 3배 종가 ' + fx(m.close3, 2) + ' · 거래대금 $' + fx(m.adtv, 1) + 'M · 상장 ' + fx(m.listed_days, 0) + '일</div>';
    });
    return h + '</div>';
  }

  var TIPS = {
    M: '변동성·상대강도·추세 세 점수의 평균 (유니버스 내 상대 점수, 100=최상위)',
    V: '유니버스 내 상대 점수, 100=최상위 — 1x 지수의 최근 60일 변동성(σ60) 백분위',
    R: '유니버스 내 상대 점수, 100=최상위 — 1x 지수의 12개월 수익률(최근 1개월 제외) 백분위',
    T: '유니버스 내 상대 점수, 100=최상위 — 1x 지수의 MA50/MA200−1 백분위'
  };
  /* 열 정의: k=정렬 키, f=정렬값(그룹은 대표 종목 값으로 참여), n=숫자 열(우측 정렬) */
  var BASE = [
    { k: 'rank', t: '순위', c: 'c', f: function (g) { return g.rep.rank; }, w: 8 },
    { k: 'tk', t: '티커', c: 'l', f: function (g) { return g.rep.ticker; }, w: 22 },
    { k: 'M', t: 'M-score', c: 'n', tip: TIPS.M, f: function (g) { return g.rep.M; }, w: 13 },
    { k: 'V', t: '변동성', c: 'n', tip: TIPS.V, f: function (g) { return g.rep.p_sig; }, w: 11 },
    { k: 'R', t: '상대강도', c: 'n', tip: TIPS.R, f: function (g) { return g.rep.p_rsA; }, w: 12 },
    { k: 'T', t: '추세', c: 'n', tip: TIPS.T, f: function (g) { return g.rep.p_f1b; }, w: 11 },
    { k: 'W', t: '!', c: 'c', f: function (g) { return whyText(g) || null; }, w: 23 }
  ];
  var XKEYS = [
    function (g) { return g.rep.sig; }, function (g) { return g.rep.rsA; }, function (g) { return g.rep.f1b; }, function (g) { return g.rep.c1_ma200; },
    function (g) { return g.rep.above200; }, function (g) { return g.rep.close3; }, function (g) { return g.rep.adtv; }, function (g) { return g.rep.listed_days; },
    function (g) { var v = parseInt(g.rep.d_rank, 10); return isNaN(v) ? null : v; }, function (g) { return g.grp ? ixName(g.rep.ticker) : null; }
  ];
  function cols() {
    var c = BASE.slice();
    if (st.mode === 'det') EXTRA.forEach(function (e, i) { c.push({ k: 'x' + i, t: e[0], c: 'n', f: XKEYS[i], w: 0 }); });
    return c;
  }
  function cmp(a, b, col, dir) {
    var x = col.f(a), y = col.f(b);
    var nx = (x === null || x === undefined || (typeof x === 'number' && isNaN(x))), ny = (y === null || y === undefined || (typeof y === 'number' && isNaN(y)));
    if (nx || ny) return nx && ny ? 0 : (nx ? 1 : -1);          // 결측은 방향과 상관없이 맨 아래
    var r = (typeof x === 'string' || typeof y === 'string') ? String(x).localeCompare(String(y), 'ko') : (x - y);
    return r * dir;
  }
  function sorted(gs) {
    var col = cols().filter(function (c) { return c.k === st.sort.k; })[0] || BASE[2];
    return gs.slice().sort(function (a, b) { var r = cmp(a, b, col, st.sort.dir); return r || (a.rep.rank - b.rep.rank); });
  }
  function head() {
    var h = '<tr>';
    cols().forEach(function (c) {
      var on = st.sort.k === c.k;
      h += '<th class="' + c.c + ' s" data-s="' + c.k + '"' + (c.tip ? ' title="' + esc(c.tip) + '"' : '') + '>' + esc(c.t) + (on ? '<span class="ar">' + (st.sort.dir === -1 ? '▼' : '▲') + '</span>' : '') + '</th>';
    });
    return h + '</tr>';
  }
  function colgroup() {
    if (st.mode === 'det') return '';
    return '<colgroup>' + BASE.map(function (c) { return '<col style="width:' + c.w + '%">'; }).join('') + '</colgroup>';
  }
  /* 한 행: 그룹 대표 행(g.grp)·단일 행·멤버 행(mem=true)이 같은 열 규칙을 쓴다 */
  function rowHtml(g, i, mem) {
    var r = g.rep, wt = whyText(g), det = st.mode === 'det';
    var ic = wt ? '<span class="wh" data-w="' + esc(wt) + '">!</span>' : '';
    var rci = rcIcon(r.ticker);
    var tk = g.grp ? '<span class="nw"><span class="car">▸</span>' + esc(r.ticker) + '<span class="more">+' + (g.mem.length - 1) + '</span></span>' + rci + ic : tkLink(r.ticker) + '<span class="ics">' + rci + ic + '</span>';
    var h = '<tr class="' + (mem ? 'mr' : 'r') + '"' + (mem ? ' hidden' : ' data-i="' + i + '"') + '><td class="rk1">' + fx(r.rank, 0) + '</td><td class="tk">' + tk + '</td><td class="m n">' + fx(r.M, 1) +
      '</td><td class="sc n">' + pct(r.p_sig) + '</td><td class="sc n">' + pct(r.p_rsA) + '</td><td class="sc n">' + pct(r.p_f1b) + '</td>' +
      '<td class="wc">' + (wt ? '<span class="wr" data-w="' + esc(wt) + '">' + whyLines(g) + '</span>' : '') + '</td>';
    if (det) EXTRA.forEach(function (e) { h += '<td class="n' + (g.grp && e[2] ? ' mu' : '') + '"' + (g.grp && e[2] ? ' title="대표(거래대금 최대) 종목 ' + esc(r.ticker) + ' 값 — 펼치면 개별 값"' : '') + '>' + e[1](g) + '</td>'; });
    return h + '</tr>';
  }
  function body(rows) {
    var gs = sorted(groups(rows)), h = '', ncol = 7 + (st.mode === 'det' ? EXTRA.length : 0);
    gs.forEach(function (g, i) {
      h += rowHtml(g, i, false);
      if (g.grp) g.mem.forEach(function (m) { h += rowHtml({ rep: m, mem: [m], grp: false }, i, true); });
      var panel = (st.mode === 'sum' ? kvPanel(g) : '') + (g.grp ? memInfo(g) : '');
      if (panel) h += '<tr class="dt" hidden><td colspan="' + ncol + '"><div class="panel">' + panel + '</div></td></tr>';
    });
    return h;
  }

  /* 모든 행 높이를 가장 높은 행(사유가 3줄인 행 등)에 맞춘다 — 측정 후 --rh 로 지정, 너비가 바뀌면 다시 측정 */
  function fitRows(tbl) {
    if (!tbl) return;
    tbl.style.removeProperty('--rh');
    var rows = tbl.querySelectorAll('tbody > tr:not(.dt)'), hid = [], max = 0, i;
    for (i = 0; i < rows.length; i++) if (rows[i].hidden) { rows[i].hidden = false; hid.push(rows[i]); }
    for (i = 0; i < rows.length; i++) max = Math.max(max, rows[i].getBoundingClientRect().height);
    for (i = 0; i < hid.length; i++) hid[i].hidden = true;
    if (max > 0) tbl.style.setProperty('--rh', Math.ceil(max) + 'px');
  }
  function renderTable() {
    var rows = st.rows, t = $('rk');
    $('ttl').innerHTML = '<b>' + st.date + ' 기준</b> <span>· ' + rows.length + '종' + (st.date === D.asof ? ' · 최신' : '') + '</span>';
    $('todaybtn').hidden = (st.date === D.asof);
    $('modebtn').textContent = st.mode === 'sum' ? '상세보기' : '요약보기';
    $('modebtn').classList.toggle('on', st.mode === 'det');
    t.className = 'rk ' + (st.mode === 'sum' ? 'sum' : 'det');
    t.innerHTML = colgroup() + '<thead>' + head() + '</thead><tbody>' + body(rows) + '</tbody>';
    var nt = $('rcnote'); if (nt) { var any = rows.some(function (r) { return rcInfo(r.ticker, st.date); }); nt.hidden = !any; nt.textContent = any ? (D.rcNote || '') : ''; }
    fitRows(t);
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
    var y0 = +D.first.slice(0, 4), y1 = +D.last.slice(0, 4), ys = '', ms = '';
    for (var yy = y0; yy <= y1; yy++) ys += '<option value="' + yy + '"' + (yy === y ? ' selected' : '') + '>' + yy + '년</option>';
    for (var mm = 1; mm <= 12; mm++) ms += '<option value="' + mm + '"' + (mm === m ? ' selected' : '') + (availYM[y * 100 + mm] ? '' : ' disabled') + '>' + mm + '월</option>';
    var h = '<div class="calbar"><span class="ym"><button class="btn" id="cprev" aria-label="이전 달">‹</button><select id="cyear" aria-label="연도">' + ys + '</select><select id="cmonth" aria-label="월">' + ms + '</select><button class="btn" id="cnext" aria-label="다음 달">›</button></span>' +
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
      var nx = tr.nextElementSibling, open = nx && nx.hidden, any = false;
      while (nx && !nx.classList.contains('r')) { nx.hidden = !open; any = true; nx = nx.nextElementSibling; }
      if (any) {
        tr.classList.toggle('open', open);
        var c = tr.querySelector('.car'); if (c) c.textContent = open ? '▾' : '▸';
      }
    }
  });
  window.addEventListener('scroll', function () { pop.hidden = true; }, true);
  var rzT; window.addEventListener('resize', function () { clearTimeout(rzT); rzT = setTimeout(function () { fitRows($('rk')); }, 120); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { fitRows($('rk')); });

  $('modebtn').addEventListener('click', function () { st.mode = st.mode === 'sum' ? 'det' : 'sum'; renderTable(); });
  $('todaybtn').addEventListener('click', function () { select(D.asof); });
  $('calbox').addEventListener('click', function (e) {
    var t = e.target;
    if (t.id === 'cprev') mv(-1); else if (t.id === 'cnext') mv(1);
    else if (t.id === 'ctog') { st.calOpen = !st.calOpen; drawCal(); }
    else if (t.getAttribute && t.getAttribute('data-d')) select(t.getAttribute('data-d'));
  });

  $('calbox').addEventListener('change', function (e) {
    var t = e.target;
    if (t.id === 'cyear') {
      var ny = +t.value, nm = st.m;
      if (!availYM[ny * 100 + nm]) { nm = 0; for (var k = 1; k <= 12; k++) { if (availYM[ny * 100 + k]) { nm = k; if (ny !== +D.last.slice(0, 4)) break; } } }
      st.y = ny; st.m = nm || 1; drawCal();
    } else if (t.id === 'cmonth') { st.m = +t.value; drawCal(); }
  });
  $('rk').addEventListener('click', function (e) {
    var th = e.target.closest ? e.target.closest('th.s') : null;
    if (!th) return;
    var k = th.getAttribute('data-s');
    st.sort = { k: k, dir: st.sort.k === k ? -st.sort.dir : -1 };
    renderTable();
  });
  var h0 = (location.hash || '').slice(1);
  var start = avail[h0] ? h0 : D.asof, p0 = start.split('-');
  st.y = +p0[0]; st.m = +p0[1];
  if (/[?&]cal=0/.test(location.search)) st.calOpen = false;
  if (/[?&]mode=det/.test(location.search)) st.mode = 'det';
  drawCal(); load(start);
})();
