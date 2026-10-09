/* 장기순위 — 5개 기간 탭 · 열 머리 정렬(탭을 바꿔도 유지) · ! 는 티커 옆 아이콘 + 우측 사유 글자.
   데이터는 페이지에 내장(#ltdata, 같은 내용이 data/longterm.json). 외부 라이브러리 0. 렌더 스크립트: scripts/mm_site.py */
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('ltdata').textContent);
  var $ = function (i) { return document.getElementById(i); };
  var cur = 0, sort = { k: 'r', dir: 1 };
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function f1(x) { return x === null ? '—' : x.toFixed(1); }
  function iv(x) { return x === null ? '—' : String(x); }
  var TIPS = {
    m: '그 기간 일별 M-score의 평균 (유니버스 내 상대 점수, 100=최상위)',
    v: '그 기간 일별 변동성 점수의 평균 (유니버스 내 상대 점수, 100=최상위)',
    rs: '그 기간 일별 상대강도 점수의 평균 (유니버스 내 상대 점수, 100=최상위)',
    tr: '그 기간 일별 추세 점수의 평균 (유니버스 내 상대 점수, 100=최상위)'
  };
  var COLS = [
    { k: 'r', t: '순위', c: 'c', w: 8 }, { k: 't', t: '티커', c: 'l', w: 22 },
    { k: 'm', t: '평균<br>M-score', c: 'n', w: 13 }, { k: 'v', t: '평균<br>변동성', c: 'n', w: 11 },
    { k: 'rs', t: '평균<br>상대강도', c: 'n', w: 12 }, { k: 'tr', t: '평균<br>추세', c: 'n', w: 11 }, { k: 'w', t: '!', c: 'c', w: 23 }
  ];
  function val(r, k) { var x = r[k]; return (x === '' || x === undefined) ? null : x; }
  function sorted(rows) {
    return rows.slice().sort(function (a, b) {
      var x = val(a, sort.k), y = val(b, sort.k);
      if (x === null || y === null) { if (x === y) return 0; return x === null ? 1 : -1; }
      var r = (typeof x === 'string') ? x.localeCompare(y, 'ko') : (x - y);
      r *= sort.dir;
      if (r) return r;
      var ra = a.r === null ? 1e9 : a.r, rb = b.r === null ? 1e9 : b.r;
      return ra - rb;
    });
  }
  function tabs() {
    $('ltabs').innerHTML = D.tabs.map(function (t, i) {
      return '<button class="btn' + (i === cur ? ' on' : '') + '" data-i="' + i + '">' + t.label + '</button>';
    }).join('');
  }
  /* 사유 단축(MM-BT-CHARTS-20261011): data/longterm.json 의 w 는 구 문구라 표시할 때 바꾼다(이미 짧은 문구에는 무변화) */
  function shortW(w) {
    return String(w).replace(/거래대금 \$/g, '$').replace(/(표본 \d+)개/g, '$1').replace(/지수 이력 일부 재구성\((\d+)%\)/g, '재구성 $1%');
  }
  function lines(w) { return esc(shortW(w)).split(' · ').join('<br>'); }

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
  function render() {
    var t = D.tabs[cur];
    var h = '<colgroup>' + COLS.map(function (c) { return '<col style="width:' + c.w + '%">'; }).join('') + '</colgroup><thead><tr>' +
      COLS.map(function (c) {
        var on = sort.k === c.k;
        return '<th class="' + c.c + ' s" data-s="' + c.k + '"' + (TIPS[c.k] ? ' title="' + esc(TIPS[c.k]) + '"' : '') + '>' + c.t + (on ? '<span class="ar">' + (sort.dir === -1 ? '▼' : '▲') + '</span>' : '') + '</th>';
      }).join('') + '</tr></thead><tbody>';
    sorted(t.rows).forEach(function (r) {
      var ic = r.w ? '<span class="wh" data-w="' + esc(shortW(r.w)) + '">!</span>' : '';
      var rcv = D.rc && D.rc[r.t], rc = rcv ? '<span class="rc" data-w="' + esc('되계산 비중 ' + rcv.p + '% · 공식 지수 ' + rcv.of + '부터 · 해제 예정 ' + rcv.rel) + '">◐</span>' : '';
      h += '<tr><td class="rk1">' + (r.r === null ? '—' : r.r) + '</td><td class="tk"><a href="products/' + esc(r.t) + '.html">' + esc(r.t) + '</a><span class="ics">' + rc + ic + '</span></td><td class="m n">' + f1(r.m) +
        '</td><td class="sc n">' + iv(r.v) + '</td><td class="sc n">' + iv(r.rs) + '</td><td class="sc n">' + iv(r.tr) + '</td><td class="wc">' +
        (r.w ? '<span class="wr" data-w="' + esc(shortW(r.w)) + '">' + lines(r.w) + '</span>' : '') + '</td></tr>';
    });
    var el = $('lt'); el.className = 'rk sum'; el.innerHTML = h + '</tbody>';
    fitRows(el);
    var nt = $('rcnote'); if (nt) { var anyRc = D.rc && Object.keys(D.rc).length; nt.hidden = !anyRc; nt.textContent = anyRc ? (D.note || '') : ''; }
    var miss = t.rows.filter(function (r) { return r.m === null; }).length;
    $('ltl').innerHTML = '<b>' + esc(D.asof) + ' 기준 · ' + t.label + ' 평균</b> <span>· 최근 ' + t.k + '거래일' + (miss ? ' · 표본 부족 ' + miss + '종 "—"' : '') + '</span>';
    tabs();
  }
  var pop = $('pop');
  function showPop(el) {
    pop.textContent = el.getAttribute('data-w'); pop.hidden = false;
    var r = el.getBoundingClientRect(), w = pop.offsetWidth;
    pop.style.top = (r.bottom + 6) + 'px';
    pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + 'px';
    pop._src = el;
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('#ltabs button') : null;
    if (b) { cur = +b.getAttribute('data-i'); pop.hidden = true; render(); try { history.replaceState(null, '', '#' + D.tabs[cur].k); } catch (x) { } return; }
    var th = e.target.closest ? e.target.closest('th.s') : null;
    if (th) { var k = th.getAttribute('data-s'); sort = { k: k, dir: sort.k === k ? -sort.dir : -1 }; pop.hidden = true; render(); return; }
    var w = e.target.closest ? e.target.closest('[data-w]') : null;
    if (w) { e.stopPropagation(); if (!pop.hidden && pop._src === w) { pop.hidden = true; return; } showPop(w); return; }
    pop.hidden = true;
  });
  window.addEventListener('scroll', function () { pop.hidden = true; }, true);
  var rzT; window.addEventListener('resize', function () { clearTimeout(rzT); rzT = setTimeout(function () { fitRows($('lt')); }, 120); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { fitRows($('lt')); });
  var h0 = parseInt((location.hash || '').slice(1), 10);
  D.tabs.forEach(function (t, i) { if (t.k === h0) cur = i; });
  render();
})();
