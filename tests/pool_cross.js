// MM-PRODUCT-POOL-CHARTS-20261124 §5-4/5-5: 브라우저 엔진(groups.js)을 디스크 원값으로 돌려, 메인 표(G.table)와 종목 차트(G.series)가 같은 풀·같은 날짜에서 같은 순위를 내는지,
// 기본 상태가 저장 계열과 같은지 JSON 으로 출력한다. 사용: node tests/pool_cross.js  (test_pool.py 가 호출)
const fs = require('fs'), path = require('path');
const DOCS = path.resolve(__dirname, '..', 'docs');
const G = require(path.join(DOCS, 'assets', 'groups.js'));
G.fetchJson = (u) => Promise.resolve(JSON.parse(fs.readFileSync(path.join(DOCS, u), 'utf8')));
const cfg = JSON.parse(fs.readFileSync(path.join(DOCS, 'data', 'groups_meta.json'), 'utf8'));
(async () => {
  G.init(cfg, 'data/../', { persist: false }); G.base = '';
  await G.ensureAll();
  const out = { cases: [] };
  const last = G.cal[G.cal.length - 1], dates = [G.cal[G.cal.length - 1], G.cal[Math.floor(G.cal.length * 0.5)], G.cal[Math.floor(G.cal.length * 0.9)]];
  const POOLS = { inv: ['inv'], all: ['base', 'crypto', 'bond', 'intl', 'inv'], crypto: ['crypto'], base_inv: ['base', 'inv'] };
  for (const [tk, pools] of [['SQQQ', ['inv', 'all']], ['BITU', ['crypto', 'all']], ['SOXL', ['base_inv', 'all']]]) for (const pn of pools) {
    const ts = G.tickers(POOLS[pn]), s = G.series(tk, ts);
    for (const d of dates) {
      const tb = G.table(d, ts), row = tb && tb.find(x => x.ticker === tk), i = s.d.indexOf(d);
      out.cases.push({ tk, pool: pn, d, table_rank: row ? row.rank : null, table_n: tb ? tb.length : null, table_M: row ? row.M : null, series_rank: i >= 0 ? s.r[i] : null, series_n: i >= 0 ? s.n[i] : null, series_M: i >= 0 ? s.m[i] : null });
    }
  }
  out.last = last; console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(2); });
