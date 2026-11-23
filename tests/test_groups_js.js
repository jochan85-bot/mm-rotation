// 6-1(JS) · 6-5: 브라우저 엔진(docs/assets/groups.js)을 노드에서 돌려 저장된 날짜 파일과 대조한다.
//   node tests/test_groups_js.js [--py <파이썬 기준 JSON>]   종료 코드 0=통과
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..'), DOCS = path.join(ROOT, 'docs');
const G = require(path.join(DOCS, 'assets', 'groups.js'));
G.fetchJson = (u) => Promise.resolve(JSON.parse(fs.readFileSync(path.join(DOCS, u), 'utf8')));
function csv(d) { const L = fs.readFileSync(path.join(DOCS, 'data', 'scores', d + '.csv'), 'utf8').split('\n'), cols = L[1].split(','), rows = {};
  for (let i = 2; i < L.length; i++) { if (!L[i]) continue; const c = L[i].split(','), o = {}; cols.forEach((k, j) => o[k] = c[j]); rows[o.ticker] = o; } return rows; }
const cfg = JSON.parse(fs.readFileSync(path.join(DOCS, 'data', 'groups_meta.json'), 'utf8'));
(async () => {
  G.init(cfg, ''); await G.loadIndex(); await G.ensureAll();
  const base = G.tickers(['base']), dates = G.cal.filter(d => d >= '2020-01-02');
  let mx = { M: 0, p: 0 }, rankBad = 0, drBad = 0, nd = 0, bad = [];
  for (const d of dates) {
    const st = csv(d), tb = G.table(d, base), by = {}; tb.forEach(r => by[r.ticker] = r); nd++;
    const ks = Object.keys(st);
    if (ks.length !== tb.length || ks.some(k => !by[k])) { bad.push(d + ' 종목집합'); continue; }
    for (const k of ks) {
      const s = st[k], m = by[k];
      mx.M = Math.max(mx.M, Math.abs(+s.M - m.M)); mx.p = Math.max(mx.p, Math.abs(+s.p_sig - m.p_sig), Math.abs(+s.p_rsA - m.p_rsA), Math.abs(+s.p_f1b - m.p_f1b));
      if (+s.rank !== m.rank) { rankBad++; bad.push(d + ' rank ' + k); }
      if (String(s.d_rank) !== String(m.d_rank)) { drBad++; if (bad.length < 20) bad.push(d + ' d_rank ' + k + ' ' + s.d_rank + '/' + m.d_rank); }
    }
  }
  console.log(JSON.stringify({ days: nd, maxM: mx.M, maxP: mx.p, rankBad, drBad, bad: bad.slice(0, 10) }));
  process.exit(mx.M < 1e-6 && mx.p < 1e-6 && !rankBad && !drBad ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
