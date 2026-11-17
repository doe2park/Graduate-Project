/* Headless desktop check of "pair once" on the headset entry card (scan-xr.html, desktop page, NOT a headset and NOT a real tunnel).
   The page runs at its real public origin (https://doe2park.github.io, answered from this checkout by Playwright), the announced
   address is mocked (api.github.com / raw.githubusercontent.com answered by Playwright), and the "tunnel" hosts are forwarded to a
   local --mock server this script starts and stops itself (--no-tts --no-stt, its own --usage-dir). Steps and screenshots:
     01 not connected  ·  02 connected after typing the code  ·  03 auto-connected on a second visit after a server restart
     with a new code and a new address  ·  04 laptop not running (Ask off, the rest of the page as without Ask)  ·  05 forgotten
     PYTHON=~/.venvs/ask-twin/bin/python PLAYWRIGHT_MODULE=/path/to/playwright-core node tests/xr-ask-pairing-smoke.cjs [outDir]
   Silent: Chrome runs with --mute-audio and an init script that stubs speechSynthesis, HTMLMediaElement.play and AudioContext. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), os = require('node:os'), {spawn} = require('node:child_process');
const ROOT = path.join(__dirname, '..'), PUB = 'https://doe2park.github.io/Graduate-Project/';
const OUT = process.argv[2] || path.join(ROOT, 'work', 'ask-twin', 'pairing-shots');
const PY = process.env.PYTHON || path.join(os.homedir(), '.venvs', 'ask-twin', 'bin', 'python');
const PORT = Number(process.env.SMOKE_PORT || 8791);
const TUN1 = 'https://calm-river-two-words.trycloudflare.com', TUN2 = 'https://fresh-lake-four-words.trycloudflare.com';
const TYPES = {html: 'text/html', js: 'text/javascript', mjs: 'text/javascript', wasm: 'application/wasm', png: 'image/png', jpg: 'image/jpeg', svg: 'image/svg+xml', json: 'application/json', glb: 'model/gltf-binary', css: 'text/css', bin: 'application/octet-stream'};
const SILENT = `(() => { try { const s = {speak() {}, cancel() {}, pause() {}, resume() {}, getVoices: () => [], speaking: false, pending: false, onvoiceschanged: null, addEventListener() {}, removeEventListener() {}};
  Object.defineProperty(window, 'speechSynthesis', {value: s, configurable: true}); } catch (e) {}
  try { HTMLMediaElement.prototype.play = function () { return Promise.resolve(); }; } catch (e) {}
  try { delete window.AudioContext; delete window.webkitAudioContext; window.AudioContext = undefined; window.webkitAudioContext = undefined; } catch (e) {} })();`;

function startServer(code, usageDir) {
  const p = spawn(PY, [path.join(ROOT, 'scripts', 'ask_twin_server.py'), '--mock', '--no-tts', '--no-stt', '--port', String(PORT), '--code', code,
    '--usage-dir', usageDir, '--idle-minutes', '0'], {cwd: ROOT, env: Object.assign({}, process.env, {ASK_TWIN_NO_REEXEC: '1'}), stdio: ['ignore', 'pipe', 'pipe']});
  let log = '';
  p.stdout.on('data', d => { log += d; }); p.stderr.on('data', d => { log += d; });
  return {p, log: () => log, ready: (async () => { for (let i = 0; i < 120; i++) { try { const r = await fetch(`http://127.0.0.1:${PORT}/api/health`); if (r.ok) return; } catch (e) {} await new Promise(r => setTimeout(r, 500)); } throw new Error('server did not start:\n' + log); })()};
}
const stop = s => new Promise(res => { if (!s || s.p.exitCode != null) return res(); s.p.once('exit', res); s.p.kill('SIGTERM'); });

(async () => {
  fs.mkdirSync(OUT, {recursive: true});
  const usageDir = path.join(OUT, 'usage-' + Date.now());   // the smoke's own paired-devices.json (left for inspection)
  fs.mkdirSync(usageDir, {recursive: true});
  const net = {announce: TUN1, laptop: 'up'}, report = {};
  let server = startServer('48219067', usageDir);
  await server.ready;
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--mute-audio', '--enable-webgl', '--ignore-gpu-blocklist', '--use-angle=metal']});
  const context = await browser.newContext({viewport: {width: 1024, height: 640}});
  await context.addInitScript(SILENT);
  await context.route(/^https:\/\/doe2park\.github\.io\/Graduate-Project\//, r => {
    const rel = decodeURIComponent(new URL(r.request().url()).pathname.replace('/Graduate-Project/', '')) || 'index.html';
    const f = path.join(ROOT, rel.endsWith('/') ? rel + 'index.html' : rel);
    if (!f.startsWith(ROOT) || /\/(scan-assets|scans)\//.test(f) && /\.(jpe?g|webp|png)$/i.test(f)) return r.abort();   // no capture photos in the shots
    if (!fs.existsSync(f)) return r.fulfill({status: 404, body: 'not found'});
    r.fulfill({status: 200, body: fs.readFileSync(f), contentType: TYPES[path.extname(f).slice(1)] || 'application/octet-stream'});
  });
  const seenAtGithub = [];
  await context.route(/^https:\/\/(api\.github\.com|raw\.githubusercontent\.com)\//, r => {
    seenAtGithub.push({url: r.request().url(), headers: r.request().headers()});
    r.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({server: net.announce, updated: new Date().toISOString()})});
  });
  const toLaptop = [];
  await context.route(/^https:\/\/[a-z0-9-]+\.trycloudflare\.com\//, async r => {
    const q = r.request(), u = new URL(q.url());
    toLaptop.push({host: u.host, method: q.method(), path: u.pathname + u.search, headers: q.headers()});
    if (net.laptop !== 'up' || u.origin !== net.announce) return r.abort('connectionrefused');
    const resp = await r.fetch({url: `http://127.0.0.1:${PORT}${u.pathname}${u.search}`});
    await r.fulfill({response: resp});
  });
  const page = await context.newPage(), errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  const askState = () => page.evaluate(() => { const i = xrInspection().ask, b = document.getElementById('askBox'); return {on: i.on, state: b?.dataset.state || null, line: document.getElementById('askState')?.textContent || null, base: i.base || null, paired: i.paired, mode: i.health?.mode || null}; });
  const settle = (want, ms = 60000) => page.waitForFunction(w => { const b = document.getElementById('askBox'); return b && w.includes(b.dataset.state); }, want, {timeout: ms});
  const URL1 = PUB + 'scan-xr.html?sensors=demo&layers=duct';
  try {
    // 01: first visit, nothing stored: one collapsed line; opened, it shows the code field
    await page.goto(URL1, {waitUntil: 'load'});
    await settle(['off']);
    await page.click('#askBox > summary');
    report.s01 = await askState();
    assert.equal(report.s01.line, 'Not connected');
    await page.screenshot({path: path.join(OUT, '01-not-connected.png')});
    // 02: type the code as shown ("4821 9067"), Connect: paired, Ask on in place (no reload), MOCK
    await page.fill('#askCode', '4821 9067');
    await page.click('#askConnectBtn');
    await settle(['connected']);
    report.s02 = await askState();
    assert.deepEqual([report.s02.on, report.s02.base, report.s02.paired, report.s02.mode, report.s02.line], [true, TUN1, true, 'mock', 'Connected · MOCK']);
    const stored = await page.evaluate(() => localStorage.getItem('askTwin.pairing.v1'));
    const token = JSON.parse(stored).token;
    assert.match(token, /^[A-Za-z0-9_-]{43}$/);
    assert.ok(!page.url().includes(token) && !page.url().includes('48219067'), 'no code or token in the address');
    const file = fs.readFileSync(path.join(usageDir, 'paired-devices.json'), 'utf8');
    assert.ok(!file.includes(token) && /"sha256": "[0-9a-f]{64}"/.test(file), 'laptop keeps only the hash');
    await page.screenshot({path: path.join(OUT, '02-connected-after-code.png')});
    // 03: restart the laptop with a NEW code and a NEW announced address; second visit connects by itself
    await stop(server); server = startServer('31415926', usageDir); await server.ready; net.announce = TUN2;
    await page.goto(URL1, {waitUntil: 'load'});
    await settle(['connected']);
    report.s03 = await askState();
    assert.deepEqual([report.s03.on, report.s03.base, report.s03.line], [true, TUN2, 'Connected · MOCK']);
    // a question goes through with the token (pick a duct element when the layer is there; else check the token on /api/pair/check only)
    const tokReq = toLaptop.filter(x => x.host === new URL(TUN2).host && x.path === '/api/pair/check');
    assert.ok(tokReq.length && tokReq.every(x => x.headers['x-ask-token'] === token && !x.headers['x-ask-code']));
    await page.screenshot({path: path.join(OUT, '03-auto-connected-second-visit.png')});
    // 04: laptop not running: plain words, Try again, Ask stays off, the rest of the page loads as without Ask
    net.laptop = 'down';
    await page.goto(URL1, {waitUntil: 'load'});
    await settle(['down']);
    report.s04 = await askState();
    assert.deepEqual([report.s04.on, report.s04.line], [false, 'Laptop not running']);
    report.s04.note = await page.evaluate(() => document.getElementById('askStateNote').textContent);
    assert.match(report.s04.note, /Everything else on this page works/);
    await page.waitForFunction(() => { try { return xrInspection().layers.duct?.loaded; } catch (e) { return false; } }, null, {timeout: 180000}).catch(() => {});
    report.s04.ductLoaded = await page.evaluate(() => !!xrInspection().layers.duct?.loaded);
    await page.screenshot({path: path.join(OUT, '04-laptop-not-running.png')});
    // 05: laptop back; Forget this laptop under More options -> unpaired here and on the laptop
    net.laptop = 'up';
    await page.click('#askAutoRetry');
    await settle(['connected']);
    await page.evaluate(() => { document.getElementById('moreOpts').open = true; document.getElementById('askForgetBtn').scrollIntoView(); });
    await page.screenshot({path: path.join(OUT, '05-more-options-forget.png')});
    await Promise.all([page.waitForNavigation({waitUntil: 'load'}), page.click('#askForgetBtn')]);
    await settle(['off']);
    report.s05 = await askState();
    assert.equal(await page.evaluate(() => localStorage.getItem('askTwin.pairing.v1')), null);
    assert.ok(!/"sha256"/.test(fs.readFileSync(path.join(usageDir, 'paired-devices.json'), 'utf8')), 'the laptop deleted the hash too');
    // nothing secret ever went to GitHub or into a URL
    assert.ok(seenAtGithub.every(x => !x.headers['x-ask-token'] && !x.headers['x-ask-code']));
    assert.ok(toLaptop.every(x => !x.path.includes(token) && !/code=/.test(x.path)));
    assert.ok(!server.log().includes(token), 'the server log never shows the token');
    report.requestsToLaptop = [...new Set(toLaptop.map(x => x.method + ' ' + x.path.split('?')[0]))];
    assert.deepEqual(errors, []);
    report.ok = true;
  } catch (e) { report.ok = false; report.error = String(e.stack || e); report.errors = errors; report.serverLog = server.log().slice(-2000); process.exitCode = 1; }
  finally {
    fs.writeFileSync(path.join(OUT, 'pairing-smoke.json'), JSON.stringify(report, null, 1));
    console.log(JSON.stringify(report, null, 1));
    await browser.close(); await stop(server);
  }
})();
