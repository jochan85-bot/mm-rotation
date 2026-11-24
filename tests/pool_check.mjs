// MM-PRODUCT-POOL-CHARTS-20261124 §5-3: 종목 페이지 풀 선택 헤드리스 렌더(모바일·데스크톱) — 결과 JSON 을 출력한다(값 대조는 tests/test_pool.py).
//   node tests/pool_check.mjs [출력 폴더]    종료 코드 0 = 오류·깨짐 0
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
const ROOT = path.resolve(import.meta.dirname, '..'), OUT = process.argv[2] || '/tmp/mm_pool_render';
mkdirSync(OUT, { recursive: true });
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 8792, DBG = 9345;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const srv = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1', '--directory', path.join(ROOT, 'docs')], { stdio: 'ignore' });
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${DBG}`, '--user-data-dir=/tmp/chrome_mm_pool', '--no-first-run', '--disable-gpu', 'about:blank'], { stdio: 'ignore' });
function cleanup() { try { srv.kill(); } catch (e) { } try { chrome.kill(); } catch (e) { } }
process.on('exit', cleanup);
async function ws() {
  for (let i = 0; i < 50; i++) { try { const r = await fetch(`http://127.0.0.1:${DBG}/json/list`); const j = await r.json(); const p = j.find(x => x.type === 'page'); if (p) return p.webSocketDebuggerUrl; } catch (e) { } await sleep(200); }
  throw new Error('chrome 연결 실패');
}
const VIEWS = { mobile: [390, 844, 3], desktop: [1280, 900, 1] };
// [라벨, 티커, localStorage 저장값(null = 비움), 클릭 동작(선택)]
const SC = [
  ['SOXL_기본', 'SOXL', null], ['SOXL_기본+인버스', 'SOXL', ['base', 'inv']], ['SOXL_전부', 'SOXL', ['base', 'crypto', 'bond', 'intl', 'inv']],
  ['SQQQ_전부', 'SQQQ', null], ['SQQQ_인버스만', 'SQQQ', ['inv']], ['BITU_전부', 'BITU', null], ['BITU_크립토만', 'BITU', ['crypto']],
  ['TMF_기본상태', 'TMF', null], ['JPNU_기본상태', 'JPNU', null], ['TQQQ_기본', 'TQQQ', null], ['GDXU_기본', 'GDXU', null],
  ['SOXL_저장값_다른종목에서', 'SOXL', ['inv']],            // 저장값에 자기 그룹(base)이 없어도 고정으로 켜진다
];
const CHECK = `(() => {
  const g = (id) => { const e = document.getElementById(id); return e ? e.textContent : null; };
  const btns = [...document.querySelectorAll('.rangebar .gbar button')].map(b => ({ g: b.dataset.g, on: b.classList.contains('on'), lock: b.classList.contains('lock'), pressed: b.getAttribute('aria-pressed'), dis: b.disabled }));
  const pc = document.getElementById('pchart');
  return { btns, pstat: g('pstat'), readout: g('creadout'), basis: g('pbasis'), pfail: !!(pc && pc.querySelector('.pfail') && pc.querySelector('.pfail').textContent.includes('불러오지')),
    pcanvas: pc ? pc.querySelectorAll('canvas').length : -1, pnote: pc ? pc.textContent.slice(0, 40) : null, csvg: !!document.getElementById('csvg'),
    cpaths: document.querySelectorAll('#csvg path').length, sw: document.documentElement.scrollWidth, iw: window.innerWidth, store: localStorage.getItem('mm_pool_v1'),
    barW: (document.querySelector('.rangebar') || {getBoundingClientRect: () => ({width: 0})}).getBoundingClientRect().width }; })()`;
(async () => {
  const sock = new WebSocket(await ws()); await new Promise(r => sock.addEventListener('open', r));
  let id = 0; const pend = new Map(), errs = [];
  sock.addEventListener('message', (m) => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); }
    if (d.method === 'Runtime.exceptionThrown') errs.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
    if (d.method === 'Runtime.consoleAPICalled' && d.params.type === 'error') errs.push('console.error ' + JSON.stringify(d.params.args.map(a => a.value || a.description)).slice(0, 160)); });
  const send = (method, params = {}) => new Promise(res => { const i = ++id; pend.set(i, res); sock.send(JSON.stringify({ id: i, method, params })); });
  const ev = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result.value;
  await send('Page.enable'); await send('Runtime.enable');
  const results = []; let fail = 0;
  for (const [vn, vw] of Object.entries(VIEWS)) {
    await send('Emulation.setDeviceMetricsOverride', { width: vw[0], height: vw[1], deviceScaleFactor: vw[2] > 1 ? 2 : 1, mobile: vw[2] > 1 });
    for (const [label, t, store] of SC) {
      errs.length = 0;
      const url = `http://127.0.0.1:${PORT}/products/${t}.html`;
      await send('Page.navigate', { url }); await sleep(600);
      await ev(store ? `localStorage.setItem('mm_pool_v1', ${JSON.stringify(JSON.stringify(store))})` : `localStorage.removeItem('mm_pool_v1')`);
      await send('Page.navigate', { url }); await sleep(3500);
      const v = await ev(CHECK);
      const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
      writeFileSync(path.join(OUT, `${label}_${vn}.png`), Buffer.from(shot.result.data, 'base64'));
      const r = { label, t, view: vn, store, errs: errs.slice(0, 3), ...v };
      // 자기 그룹(잠금) 버튼 클릭 → 변화 없음
      const own = v.btns.find(b => b.lock);
      if (own) { await ev(`document.querySelector('.rangebar .gbar button[data-g="${own.g}"]').click()`); await sleep(300); const a = await ev(CHECK); r.lockClick = { before: v.btns.map(b => b.on).join(), after: a.btns.map(b => b.on).join(), store: a.store }; }
      // 켜고 끌 수 있는 그룹 1개 토글(첫 비잠금 버튼) → 숫자 갱신
      const other = v.btns.find(b => !b.lock && !b.dis);
      if (other) { await ev(`document.querySelector('.rangebar .gbar button[data-g="${other.g}"]').click()`); await sleep(3500); const a = await ev(CHECK);
        r.toggle = { g: other.g, was: other.on, now: a.btns.find(b => b.g === other.g).on, pstat: a.pstat, readout: a.readout, store: a.store, csvg: a.csvg }; }
      r.bad = r.errs.length > 0 || r.pfail || !r.csvg || r.sw > r.iw + 1 || r.btns.length !== 5 || !r.pstat || /불러오는/.test(r.pstat) || r.pcanvas < 1;
      if (r.bad) fail++; results.push(r);
    }
  }
  writeFileSync(path.join(OUT, 'pool_result.json'), JSON.stringify(results, null, 1));
  console.log(JSON.stringify({ n: results.length, fail, out: OUT }));
  cleanup(); process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); cleanup(); process.exit(2); });
