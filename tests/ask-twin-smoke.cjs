/* Headless end-to-end check of the Ask-the-twin panel against a running server (mock or live).
     python3 scripts/ask_twin_server.py --mock &
     PLAYWRIGHT_MODULE=/path/to/playwright-core [CHROME_EXECUTABLE=...] node tests/ask-twin-smoke.cjs [http://127.0.0.1:8765]
   Loads lighting + duct + fire, picks a recessed light under the demo leak pipe with a real canvas click,
   asks the three example questions and saves 1440x900 screenshots to work/ask-twin/shots/ (ignored).
   FAKE_AUDIO=/abs/question.wav also drives push-to-talk through Chromium's fake microphone (server STT must be on). */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const BASE = process.argv[2] || 'http://127.0.0.1:8765';
const OUT = path.join(__dirname, '..', 'work', 'ask-twin', 'shots');

async function pick(page, c, offset) {
  return page.evaluate(async ({c, offset}) => {
    const {THREE, camera, controls} = twinViewerApi, v3 = new THREE.Vector3(...c);
    controls.target.copy(v3); camera.position.set(c[0] + offset[0], c[1] + offset[1], c[2] + offset[2]); controls.update();
    await new Promise(r => setTimeout(r, 500));
    const cv = document.querySelector('canvas'), r = cv.getBoundingClientRect(), p = v3.clone().project(camera);
    return {x: r.left + (p.x + 1) / 2 * r.width, y: r.top + (1 - p.y) / 2 * r.height};
  }, {c, offset});
}

async function ask(page, i) {
  await page.click(`#atEx button[data-i="${i}"]`);
  await page.waitForFunction(() => /verified/.test(document.getElementById('atFoot').innerText) || document.querySelector('#atCard.err'), null, {timeout: 120000});
  await page.waitForTimeout(1200);   // camera fly + highlight
  return page.evaluate(() => ({card: document.getElementById('atCard').innerText, foot: document.getElementById('atFoot').innerText,
    err: !!document.querySelector('#atCard.err'), chips: document.querySelectorAll('#atCard .at-chip[data-id]').length,
    bad: document.querySelectorAll('#atCard .at-chip.bad').length, marker: getComputedStyle(document.getElementById('askTwinMarker')).display}));
}

(async () => {
  fs.mkdirSync(OUT, {recursive: true});
  const audio = process.env.FAKE_AUDIO ? ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${process.env.FAKE_AUDIO}`] : [];
  const browser = await chromium.launch({executablePath: process.env.CHROME_EXECUTABLE || undefined, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', ...audio]});
  const context = await browser.newContext({viewport: {width: 1440, height: 900}, deviceScaleFactor: 1});
  if (audio.length) await context.grantPermissions(['microphone'], {origin: BASE});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.goto(BASE + '/' + (process.env.ASK_CODE ? '?code=' + encodeURIComponent(process.env.ASK_CODE) : ''), {waitUntil: 'load'});   // ASK_CODE = the code the server printed (or start it with --no-code)
  await page.waitForFunction(() => window.twinViewerApi && document.getElementById('askTwin') && !/connecting/.test(document.getElementById('atMode').textContent));
  const mode = await page.textContent('#atMode');
  await page.evaluate(async () => { try { dismissWelcome(); } catch {} for (const k of ['lighting', 'duct', 'fire']) await toggleLayer(k); });
  // 1) water stain: recessed light 12442 under the demo leak pipe (fire 278123), viewed from below the ceiling
  let at = await pick(page, [-33.05, 7.99, -17.4], [5, -3.2, 5]);
  await page.mouse.click(at.x, at.y);
  assert.equal(await page.evaluate(() => twinViewerApi.selected()), '12442', 'real canvas click should select the light');
  await page.fill('#atQ', '');
  const leak = await ask(page, 0);
  await page.screenshot({path: path.join(OUT, '1-water-stain.png')});
  assert.ok(!leak.err && /Most likely source|evidence/i.test(leak.card) && /278123/.test(leak.card), 'leak answer cites the demo pipe');
  assert.equal(leak.bad, 0); assert.equal(leak.marker, 'block');
  // 2) valve, same selection
  const valve = await ask(page, 1);
  await page.screenshot({path: path.join(OUT, '2-shutoff-valve.png')});
  assert.ok(!valve.err && /valve/i.test(valve.card));
  // 3) what feeds this duct: spiral duct 401233 (demo airflow sensor anchor)
  at = await pick(page, [-18.92, 8.3, 0.61], [6, 4, 6]);
  await page.evaluate(() => twinViewerApi.select('401233'));
  const feed = await ask(page, 2);
  await page.screenshot({path: path.join(OUT, '3-what-feeds-duct.png')});
  assert.ok(!feed.err && /Terminal unit|air/i.test(feed.card));
  let voice = null;
  if (audio.length) {   // 4) push-to-talk: hold the mic while the fake device plays the question, release, expect an answer
    await page.evaluate(() => { twinViewerApi.select('12442'); document.getElementById('atFoot').textContent = ''; document.getElementById('atQ').value = ''; });
    const box = await page.locator('#atMic').boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.waitForFunction(() => /Listening/.test(document.getElementById('atQ').placeholder), null, {timeout: 30000});
    await page.waitForTimeout(4500); await page.mouse.up();
    await page.waitForFunction(() => /verified/.test(document.getElementById('atFoot').innerText) && !document.querySelector('#atAsk:disabled'), null, {timeout: 120000});
    await page.waitForTimeout(800);
    voice = await page.evaluate(() => ({q: document.getElementById('atQ').value, card: document.getElementById('atCard').innerText.slice(0, 200)}));
    await page.screenshot({path: path.join(OUT, '4-push-to-talk.png')});
    assert.match(voice.q, /valve/i, 'transcript should contain the spoken question');
  }
  console.log(JSON.stringify({mode, leak: leak.foot, valve: valve.foot, feed: feed.foot, voice, errors}, null, 1));
  assert.deepEqual(errors, []);
  await browser.close();
  console.log('ask-twin smoke OK ->', OUT);
})().catch(e => { console.error(e); process.exit(1); });
