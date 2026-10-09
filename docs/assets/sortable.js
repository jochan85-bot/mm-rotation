/* 종목 목록 표 — 열 머리 클릭 정렬(처음 누르면 오름차순, 같은 열을 다시 누르면 내림차순). 외부 라이브러리 0 */
(function () {
  'use strict';
  var t = document.getElementById('dir'); if (!t) return;
  var ths = Array.prototype.slice.call(t.querySelectorAll('thead th')), cur = { c: 0, dir: 1 };
  function paint() { ths.forEach(function (h, i) { var a = h.querySelector('.ar'); if (a) a.remove(); if (i === cur.c) { var s = document.createElement('span'); s.className = 'ar'; s.textContent = cur.dir === 1 ? '▲' : '▼'; h.appendChild(s); } }); }
  function sort(c) {
    cur.dir = (cur.c === c) ? -cur.dir : 1; cur.c = c;
    var tb = t.tBodies[0], rows = Array.prototype.slice.call(tb.rows);
    rows.sort(function (a, b) {
      var x = a.cells[c].textContent.trim(), y = b.cells[c].textContent.trim();
      var r = x.localeCompare(y, 'ko'); if (r === 0) r = a.cells[0].textContent.localeCompare(b.cells[0].textContent);
      return r * cur.dir;
    });
    rows.forEach(function (r) { tb.appendChild(r); }); paint();
  }
  ths.forEach(function (h, i) { h.addEventListener('click', function () { sort(i); }); });
  paint();
})();
