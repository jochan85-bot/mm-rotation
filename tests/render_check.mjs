// 6-4: 그룹 조합 5가지 × 모바일·데스크톱 헤드리스 렌더 — 표 깨짐 0 점검(+ 스크린샷). 노드 22+ (전역 WebSocket 사용), 구글 크롬 필요.
//   node tests/render_check.mjs [출력 폴더]    종료 코드 0 = 깨짐 0
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
const ROOT = path.resolve(import.meta.dirname, '..'), OUT = process.argv[2] || '/tmp/mm_render';
mkdirSync(OUT, { recursive: true });
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 8791, DBG = 9344;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const srv = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1', '--directory', path.join(ROOT, 'docs')], { stdio: 'ignore' });
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${DBG}`, '--user-data-dir=/tmp/chrome_mm_render', '--no-first-run', '--disable-gpu', 'about:blank'], { stdio: 'ignore' });
function cleanup() { try { srv.kill(); } catch (e) { } try { chrome.kill(); } catch (e) { } }
process.on('exit', cleanup);
async function ws() {
  for (let i = 0; i < 50; i++) { try { const r = await fetch(`http://127.0.0.1:${DBG}/json/list`); const j = await r.json(); const p = j.find(x => x.type === 'page'); if (p) return p.webSocketDebuggerUrl; } catch (e) { } await sleep(300); }
  throw new Error('chrome 연결 실패');
}
const COMBOS = { '기본': 'base', '기본+인버스': 'base,inv', '기본+크립토': 'base,crypto', '전부': 'base,crypto,bond,intl,inv', '인버스만': 'inv' };
const VIEWS = { mobile: [390, 844, 3], desktop: [1280, 900, 1] };
const CHECK = `(() => {
  const out = { errs: [], tables: [] };
  document.querySelectorAll('table.rk').forEach(t => {
    const hc = t.querySelectorAll('thead th').length, rows = [...t.querySelectorAll('tbody > tr')].filter(r => !r.classList.contains('dt') && !r.hidden);
    let bad = 0; rows.forEach(r => { if (r.children.length !== hc) bad++; });
    out.tables.push({ id: t.id, head: hc, rows: rows.length, badRows: bad, w: Math.round(t.getBoundingClientRect().width) });
  });
  out.sw = document.documentElement.scrollWidth; out.iw = window.innerWidth;
  const ge = document.getElementById('gempty'); out.gempty = ge ? !ge.hidden : null;
  const on = [...document.querySelectorAll('#gbar button.on')].map(b => b.dataset.g); out.on = on;
  out.ncnt = (document.getElementById('ncnt') || {}).textContent || null; out.ttl = (document.getElementById('ttl') || document.getElementById('ltl') || {}).textContent || '';
  out.chips = document.querySelectorAll('.gc').length;
  return out; })()`;
(async () => {
  const sock = new WebSocket(await ws()); await new Promise(r => sock.addEventListener('open', r));
  let id = 0; const pend = new Map(), errs = [];
  sock.addEventListener('message', (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); }
    if (d.method === 'Runtime.exceptionThrown') errs.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
    if (d.method === 'Runtime.consoleAPICalled' && d.params.type === 'error') errs.push('console.error ' + JSON.stringify(d.params.args.map(a => a.value || a.description)).slice(0, 160)); });
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pend.set(i, res); sock.send(JSON.stringify({ id: i, method, params })); });
  await send('Page.enable'); await send('Runtime.enable');
  const results = []; let fail = 0;
  async function visit(label, url, vw, vname) {
    errs.length = 0;
    await send('Emulation.setDeviceMetricsOverride', { width: vw[0], height: vw[1], deviceScaleFactor: vw[2] > 1 ? 2 : 1, mobile: vw[2] > 1 });
    await send('Page.navigate', { url }); await sleep(2800);
    const r = await send('Runtime.evaluate', { expression: CHECK, returnByValue: true }); const v = r.result.result.value;
    const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    const f = path.join(OUT, `${label}_${vname}.png`.replace(/[^\w.가-힣-]/g, '_')); writeFileSync(f, Buffer.from(shot.result.data, 'base64'));
    const bad = (v.tables || []).some(t => t.badRows > 0) || v.sw > v.iw + 1 || errs.length > 0;
    results.push({ label, view: vname, url: url.replace(/^http:\/\/127.0.0.1:\d+\//, ''), bad, errs: errs.slice(0, 3), ...v }); if (bad) fail++;
  }
  for (const [vn, vw] of Object.entries(VIEWS)) {
    for (const [cn, q] of Object.entries(COMBOS)) {
      await visit('index_' + cn, `http://127.0.0.1:${PORT}/index.html?g=${q}`, vw, vn);
      await visit('longterm_' + cn, `http://127.0.0.1:${PORT}/longterm.html?g=${q}#20`, vw, vn);
    }
    await visit('index_전부끔', `http://127.0.0.1:${PORT}/index.html?g=`, vw, vn);
    await visit('index_전부_2024', `http://127.0.0.1:${PORT}/index.html?g=base,crypto,bond,intl,inv#2024-06-14`, vw, vn);
    await visit('product_SOXL', `http://127.0.0.1:${PORT}/products/SOXL.html`, vw, vn);
    await visit('product_SQQQ', `http://127.0.0.1:${PORT}/products/SQQQ.html`, vw, vn);
    await visit('product_BITU', `http://127.0.0.1:${PORT}/products/BITU.html`, vw, vn);
  }
  writeFileSync(path.join(OUT, 'render_result.json'), JSON.stringify(results, null, 1));
  console.log(JSON.stringify({ n: results.length, fail, out: OUT, sample: results.slice(0, 2).map(r => ({ label: r.label, view: r.view, tables: r.tables, on: r.on, ncnt: r.ncnt, chips: r.chips, gempty: r.gempty })) }));
  cleanup(); process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); cleanup(); process.exit(2); });
