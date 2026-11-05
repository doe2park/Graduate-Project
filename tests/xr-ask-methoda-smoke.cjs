/* Headless desktop check of "Method A": the PUBLIC page origin (https://doe2park.github.io/Graduate-Project/mr/?ask=1&server=...)
   with only the AI calls going to the laptop server. The github.io requests are answered from this checkout by Playwright
   (context.route), so the page runs with the real public origin and its CORS / Private Network Access preflights hit the
   laptop server exactly as in the headset. Desktop MR simulation only: NOT a headset test.
     python3 scripts/ask_twin_server.py --mock --lan          # prints https://<lan-ip>:8765
     PLAYWRIGHT_MODULE=/path/to/playwright-core [FAKE_AUDIO=/abs/question.wav] node tests/xr-ask-methoda-smoke.cjs https://<lan-ip>:8765
   The laptop's self-signed certificate is accepted for this test browser only (ignoreHTTPSErrors). */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const SERVER = process.argv[2] || 'https://192.168.68.52:8765';
const OUT = process.argv[3] || path.join(__dirname, '..', 'work', 'ask-twin', 'methoda-shots');
const ROOT = path.join(__dirname, '..'), PUB = 'https://doe2park.github.io/Graduate-Project/';
const DIFFUSER = '388279';
const TYPES = {html: 'text/html', js: 'text/javascript', mjs: 'text/javascript', wasm: 'application/wasm', png: 'image/png', jpg: 'image/jpeg', svg: 'image/svg+xml', json: 'application/json', glb: 'model/gltf-binary', css: 'text/css', bin: 'application/octet-stream'};

(async () => {
  fs.mkdirSync(OUT, {recursive: true});
  const args = ['--enable-webgl', '--ignore-gpu-blocklist', '--use-angle=metal', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'];
  if (process.env.FAKE_AUDIO) args.push('--use-file-for-fake-audio-capture=' + process.env.FAKE_AUDIO);
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', args});
  const context = await browser.newContext({viewport: {width: 1400, height: 850}, ignoreHTTPSErrors: true});
  // Chrome's Local Network Access: a public page calling a private-LAN address needs the user's 'local network' permission
  // (a prompt on the 2D page in a real browser; granted here). The server's PNA preflight answer is still exercised.
  await context.grantPermissions(['microphone', 'local-network-access'], {origin: 'https://doe2park.github.io'});
  const toLaptop = [], preflights = [];
  await context.route(/^https:\/\/doe2park\.github\.io\/Graduate-Project\//, r => {
    const rel = decodeURIComponent(new URL(r.request().url()).pathname.replace('/Graduate-Project/', '')) || 'index.html';
    let f = path.join(ROOT, rel.endsWith('/') ? rel + 'index.html' : rel);
    if (!f.startsWith(ROOT) || /\/(scan-assets|scans)\//.test(f) && /\.(jpe?g|webp|png)$/i.test(f)) return r.abort();
    if (!fs.existsSync(f)) return r.fulfill({status: 404, body: 'not found'});
    r.fulfill({status: 200, body: fs.readFileSync(f), contentType: TYPES[path.extname(f).slice(1)] || 'application/octet-stream'});
  });
  const page = await context.newPage(), errors = [];
  page.on('request', q => { if (q.url().startsWith(SERVER)) toLaptop.push(q.method() + ' ' + new URL(q.url()).pathname); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|net::/.test(m.text())) errors.push('console: ' + m.text()); });
  const report = {server: SERVER};
  try {
    const url = PUB + 'mr/?ask=1&scene=air&layers=duct&server=' + encodeURIComponent(SERVER);
    await page.goto(url, {waitUntil: 'load'});
    await page.waitForFunction(() => { try { const i = xrInspection(); return i.layers.duct?.loaded && i.mr?.demo && (i.ask?.health || i.ask?.healthError); } catch (e) { return false; } }, null, {timeout: 180000});
    report.pageUrl = page.url();
    let st = await page.evaluate(() => xrInspection().ask);
    assert.ok(report.pageUrl.startsWith(PUB + 'scan-xr.html'), 'the public /mr redirect kept server=');
    assert.equal(st.base, SERVER.replace(/\/$/, ''));
    assert.ok(st.health, 'health from the laptop: ' + st.healthError);
    report.health = st.health; report.note = st.note;
    report.box = await page.evaluate(() => document.getElementById('askBox').innerText);
    await page.click('#askMicBtn');
    await page.screenshot({path: path.join(OUT, '00-2d-box.png')});
    // preset level 3 through the bar
    const pick = await page.evaluate(id => xrDebug.ask.pickId(id), DIFFUSER);
    assert.equal(pick?.id, DIFFUSER);
    const t0 = Date.now();
    await page.evaluate(() => xrDebug.ask.question(3));
    st = await page.evaluate(() => xrInspection().ask);
    assert.equal(st.phase, 'answer', st.error || '');
    assert.ok(st.citations.length && st.citations.every(c => c.verified));
    report.level3 = {ms: st.answerMs, wallMs: Date.now() - t0, lead: st.lead, speechPlan: st.speechPlan};
    await page.waitForTimeout(2500);
    report.speech = await page.evaluate(() => { const a = xrInspection().ask; return {plan: a.speechPlan, engine: a.speechEngine, state: a.speech}; });
    await page.screenshot({path: path.join(OUT, '01-level3.png')});
    // point-and-ask: hold on the diffuser, speak (fake mic: FAKE_AUDIO file, else Chrome's beep), release
    const hold = await page.evaluate(id => xrDebug.ask.holdSim(id, 3500), DIFFUSER);
    report.hold = hold;
    assert.equal(hold.el, DIFFUSER); assert.equal(hold.voice, 'recording'); assert.equal(hold.ring, true); assert.equal(hold.swallowed, true);
    await page.waitForFunction(() => { const a = xrInspection().ask; return a.voice === 'ready' && !a.busy; }, null, {timeout: 60000});
    await page.waitForTimeout(500);
    st = await page.evaluate(() => xrInspection().ask);
    report.afterHold = {phase: st.phase, question: st.question, lead: st.lead, status: await page.evaluate(() => document.getElementById('status')?.textContent || '')};
    await page.screenshot({path: path.join(OUT, '02-after-hold.png')});
    report.toLaptop = [...new Set(toLaptop)];
    assert.ok(report.toLaptop.some(r => r === 'POST /api/ask'));
    assert.ok(!report.toLaptop.some(r => /\.(html|js|glb|json)$/.test(r)), 'only API calls go to the laptop');
    assert.deepEqual(errors, []);
    report.ok = true;
  } catch (e) { report.ok = false; report.error = String(e.stack || e); report.errors = errors; process.exitCode = 1; }
  finally { fs.writeFileSync(path.join(OUT, 'methoda-smoke.json'), JSON.stringify(report, null, 1)); console.log(JSON.stringify(report, null, 1)); await browser.close(); }
})();
