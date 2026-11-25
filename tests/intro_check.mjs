// MM-PRODUCT-INTRO-ENRICH-20261124 §5-4: 신규 49종 중 그룹별 대표 종목 헤드리스 렌더(모바일·데스크톱) — 소개 3문단·구성·기본 정보·깨짐·JS 오류 점검(+스크린샷).
//   node tests/intro_check.mjs [출력 폴더]    종료 코드 0 = 오류·깨짐 0
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
const ROOT = path.resolve(import.meta.dirname, '..'), OUT = process.argv[2] || '/tmp/mm_intro_render';
mkdirSync(OUT, { recursive: true });
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PORT = 8793, DBG = 9346;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const LIVE = process.env.INTRO_LIVE_BASE || '';                     // 라이브 URL 점검용(예: https://…/mm-rotation)
const TICKERS = (process.env.INTRO_ONLY || 'BITU,TMF,KORU,SQQQ,HYGU,TAWN,SMHD').split(',');
const srv = LIVE ? null : spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1', '--directory', path.join(ROOT, 'docs')], { stdio: 'ignore' });
const chrome = spawn(CHROME, ['--headless=new', `--remote-debugging-port=${DBG}`, '--user-data-dir=/tmp/chrome_mm_intro', '--no-first-run', '--disable-gpu', 'about:blank'], { stdio: 'ignore' });
function cleanup() { try { srv && srv.kill(); } catch (e) { } try { chrome.kill(); } catch (e) { } }
process.on('exit', cleanup);
async function ws() {
  for (let i = 0; i < 50; i++) { try { const r = await fetch(`http://127.0.0.1:${DBG}/json/list`); const j = await r.json(); const p = j.find(x => x.type === 'page'); if (p) return p.webSocketDebuggerUrl; } catch (e) { } await sleep(300); }
  throw new Error('chrome 연결 실패');
}
const VIEWS = { mobile: [390, 844, 3], desktop: [1280, 900, 1] };
const CHECK = `(() => {
  const ps = [...document.querySelectorAll('.intro p')].map(p => p.textContent.trim());
  const h2 = [...document.querySelectorAll('h2')].map(h => h.textContent.trim());
  const info = [...document.querySelectorAll('table.info')].map(t => t.textContent.replace(/\\s+/g, ' ').trim());
  const last = document.querySelectorAll('table.info')[document.querySelectorAll('table.info').length - 1];
  const cells = last ? [...last.querySelectorAll('tbody td, tr:nth-child(2) td')].map(td => td.textContent.trim()) : [];
  const hold = document.querySelectorAll('.hgrid .hc').length, hsum = document.querySelectorAll('.hsum li').length, empty = [...document.querySelectorAll('.empty')].map(e => e.textContent.trim());
  const risk = document.querySelectorAll('ul.risk li').length;
  return { paras: ps.length, introLen: ps.map(p => p.length), h2, cells, hold, hsum, empty, risk, sw: document.documentElement.scrollWidth, iw: window.innerWidth,
    h1: (document.querySelector('h1') || {}).textContent, stamp: (document.querySelector('.stamp') || {}).textContent }; })()`;
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
    for (const t of TICKERS) {
      errs.length = 0;
      await send('Page.navigate', { url: (LIVE || `http://127.0.0.1:${PORT}`) + `/products/${t}.html` }); await sleep(3500);
      const v = await ev(CHECK);
      const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
      writeFileSync(path.join(OUT, `${t}_${vn}.png`), Buffer.from(shot.result.data, 'base64'));
      const bad = [];
      if (errs.length) bad.push('JS오류 ' + errs[0]);
      if (v.paras !== 3) bad.push('소개 문단 ' + v.paras);
      if (!v.h2.includes('구성') || !v.h2.includes('기본 정보') || !v.h2.includes('소개')) bad.push('절 누락 ' + v.h2.join('|'));
      if (!(v.hold > 0 || v.hsum > 0) || v.empty.some(e => e.includes('확인하지 못'))) bad.push('구성 비어 있음/안내 ' + v.empty.join('|'));
      if (v.sw > v.iw + 1) bad.push(`가로 넘침 ${v.sw}>${v.iw}`);
      const fee = v.cells[3]; if (!fee || fee === '—') bad.push('보수 없음 ' + JSON.stringify(v.cells));
      if (v.risk < 2) bad.push('리스크 줄 ' + v.risk);
      if (bad.length) fail++;
      results.push({ t, view: vn, ...v, bad });
    }
  }
  writeFileSync(path.join(OUT, 'result.json'), JSON.stringify(results, null, 1));
  results.forEach(r => console.log(r.bad.length ? 'FAIL' : 'PASS', r.t, r.view, `문단${r.paras} 격자${r.hold} 요약줄${r.hsum} 리스크${r.risk} 보수[${(r.cells || [])[3] || ''}]`.slice(0, 150), r.bad.join('; ')));
  console.log(`\n${results.length - fail} PASS, ${fail} FAIL`);
  process.exit(fail ? 1 : 0);
})();
