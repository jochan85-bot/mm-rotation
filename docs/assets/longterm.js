/* 장기순위 — 5개 기간 탭. 데이터는 페이지에 내장(#ltdata, 같은 내용이 data/longterm.json). 외부 라이브러리 0. 렌더 스크립트: scripts/mm_site.py */
(function () {
  'use strict';
  var D = JSON.parse(document.getElementById('ltdata').textContent);
  var $ = function (i) { return document.getElementById(i); };
  var cur = 0;
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function f1(x) { return x === null ? '—' : x.toFixed(1); }
  function iv(x) { return x === null ? '—' : String(x); }
  var TIPS = {
    M: '그 기간 일별 M-score의 평균 (유니버스 내 상대 점수, 100=최상위)',
    V: '그 기간 일별 변동성 점수의 평균 (유니버스 내 상대 점수, 100=최상위)',
    R: '그 기간 일별 상대강도 점수의 평균 (유니버스 내 상대 점수, 100=최상위)',
    T: '그 기간 일별 추세 점수의 평균 (유니버스 내 상대 점수, 100=최상위)'
  };
  function th(k, t, cls) { return '<th class="' + (cls || '') + ' tip" data-w="' + esc(TIPS[k]) + '" title="' + esc(TIPS[k]) + '">' + t + '</th>'; }
  function tabs() {
    $('ltabs').innerHTML = D.tabs.map(function (t, i) {
      return '<button class="btn' + (i === cur ? ' on' : '') + '" data-i="' + i + '">' + t.label + '</button>';
    }).join('');
  }
  function render() {
    var t = D.tabs[cur], h = '<thead><tr><th class="c">순위</th><th class="l">티커</th>' + th('M', '평균 M-score') + th('V', '평균 변동성') + th('R', '평균 상대강도') + th('T', '평균 추세') + '<th class="l">!</th></tr></thead><tbody>';
    t.rows.forEach(function (r) {
      h += '<tr><td class="rk1">' + (r.r === null ? '—' : r.r) + '</td><td class="tk"><a href="products/' + esc(r.t) + '.html">' + esc(r.t) + '</a></td><td class="m">' + f1(r.m) +
        '</td><td class="sc">' + iv(r.v) + '</td><td class="sc">' + iv(r.rs) + '</td><td class="sc">' + iv(r.tr) + '</td><td class="wc">' +
        (r.w ? '<span class="wh" data-w="' + esc(r.w) + '">!</span><span class="wt">' + esc(r.w) + '</span>' : '') + '</td></tr>';
    });
    $('lt').innerHTML = h + '</tbody>';
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
    var w = e.target.closest ? e.target.closest('[data-w]') : null;
    if (w) { e.stopPropagation(); if (!pop.hidden && pop._src === w) { pop.hidden = true; return; } showPop(w); return; }
    pop.hidden = true;
  });
  window.addEventListener('scroll', function () { pop.hidden = true; }, true);
  var h0 = parseInt((location.hash || '').slice(1), 10);
  D.tabs.forEach(function (t, i) { if (t.k === h0) cur = i; });
  render();
})();
