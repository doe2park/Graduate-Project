/* Headless desktop check of "Ask the twin" inside the headset page (scan-xr.html?mode=ar&place=demo&sensors=demo&scene=air&ask=1),
   against a running ask server (mock or live). This is the DESKTOP MR simulation (no immersive session): the same world-locked
   canvas label, answer card, presets panel ("⋯"), glow and lit run that the headset would draw, picked through the page's real ray path.
   NOT a headset test. Silent: --mute-audio plus an init script that removes speechSynthesis voices, SpeechSynthesisUtterance, media
   playback and AudioContext (macOS speechSynthesis bypasses --mute-audio).
     python3 scripts/ask_twin_server.py --mock --port 8766 &
     PLAYWRIGHT_MODULE=/path/to/playwright-core node tests/xr-ask-smoke.cjs [http://127.0.0.1:8766] [outdir]
   Photo backdrop requests are refused so the shots show the plain desktop background (no capture photos, no people).
   Chrome with the GPU (CHROME_EXECUTABLE, default the installed Google Chrome); only the ductwork layer is loaded. */
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const BASE = process.argv[2] || 'http://127.0.0.1:8766';
const OUT = process.argv[3] || path.join(__dirname, '..', 'work', 'ask-twin', 'xr-shots');
const DIFFUSER = '388279';   // Level 1 supply diffuser, anchor of the demo comfort / CO2 sensors (air scene)
const URL_ = BASE + '/scan-xr.html?mode=ar&place=demo&sensors=demo&scene=air&layers=duct&ask=1' + (process.env.ASK_CODE ? '&code=' + encodeURIComponent(process.env.ASK_CODE) : '');   // ASK_CODE = the printed access code

(async () => {
  fs.mkdirSync(OUT, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    args: ['--enable-webgl', '--ignore-gpu-blocklist', '--use-angle=metal', '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required', '--mute-audio']});
  const context = await browser.newContext({viewport: {width: 1600, height: 900}, deviceScaleFactor: 1});
  await context.grantPermissions(['microphone'], {origin: BASE});
  await context.addInitScript(() => {   // nothing in the page can make a sound
    const noop = () => {}, fake = {speak: noop, cancel: noop, pause: noop, resume: noop, getVoices: () => [], speaking: false, pending: false, paused: false, addEventListener: noop, removeEventListener: noop};
    try { Object.defineProperty(window, 'speechSynthesis', {value: fake, configurable: false}); } catch (e) {}
    try { Object.defineProperty(window, 'SpeechSynthesisUtterance', {value: undefined, configurable: false}); } catch (e) {}
    try { HTMLMediaElement.prototype.play = function () { return Promise.resolve(); }; } catch (e) {}
    for (const k of ['AudioContext', 'webkitAudioContext', 'OfflineAudioContext']) { try { Object.defineProperty(window, k, {value: undefined, configurable: false}); } catch (e) {} }
  });
  await context.route(/\.(jpe?g|webp|png)(\?.*)?$/i, r => r.request().url().includes('/scan-assets/') || r.request().url().includes('/scans/') ? r.abort() : r.continue());
  const page = await context.newPage(), errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|net::/.test(m.text())) errors.push('console: ' + m.text()); });
  const report = {url: URL_, base: BASE};
  try {
    await page.goto(URL_, {waitUntil: 'load'});
    await page.waitForFunction(() => { try { const i = xrInspection(); return i.layers.duct?.loaded && i.sensors.ready && i.mr?.demo && i.ask?.health; } catch (e) { return false; } }, null, {timeout: 180000});
    await page.click('#askMicBtn');
    await page.waitForFunction(() => xrInspection().ask.voice === 'ready', null, {timeout: 15000}).catch(() => {});
    const hide = () => page.addStyleTag({content: '#bar,#mr,#askBox,.pill,#stats{display:none!important}'});
    const shot = async (name, note) => { const f = path.join(OUT, name); await page.screenshot({path: f}); report[name] = note; return f; };
    report.health = (await page.evaluate(() => xrInspection().ask)).health;

    // narrower desktop field of view (mouse wheel, the page's own zoom) so the card reads at screenshot size
    await page.mouse.move(800, 300); await page.mouse.wheel(0, -700); await page.waitForTimeout(200);
    // 1. pick the diffuser through the real ray path -> ONE compact label (no info card, no buttons); "⋯" opens the presets panel
    const pick = await page.evaluate(id => xrDebug.ask.pickId(id), DIFFUSER);
    assert.equal(pick?.id, DIFFUSER, 'the ray picks the diffuser');
    let st = await page.evaluate(() => xrInspection().ask);
    assert.equal(st.bar, null); assert.equal(st.chipVisible, true); assert.equal(st.infoCardVisible, false);
    assert.equal(st.el.id, DIFFUSER);
    report.voiceAfterAllowMic = st.voice;
    await hide();
    const ndcMore = await page.evaluate(() => xrDebug.ask.barButtonNdc('more'));
    assert.equal((await page.evaluate(([x, y]) => xrDebug.hoverNdc(x, y), ndcMore))?.button, 10, '⋯ on the label');
    assert.equal((await page.evaluate(([x, y]) => xrDebug.pickNdc(x, y), ndcMore)).ask, 'more');
    st = await page.evaluate(() => xrInspection().ask);
    assert.deepEqual(st.bar, ['q1', 'q2', 'q3', 'q4', 'details', 'close']);
    // hover button 3 with the desktop pointer (the same panel hit test as a controller ray)
    const ndc3 = await page.evaluate(() => xrDebug.ask.barButtonNdc(2));
    const h = await page.evaluate(([x, y]) => xrDebug.hoverNdc(x, y), ndc3);
    assert.equal(h?.panel, 'ask'); assert.equal(h.button, 2);
    await page.waitForTimeout(300);
    await shot('01-pick-ask-bar.png', 'diffuser picked: compact label + presets panel opened with ⋯ (levels 1-4, Details, Close), button 3 hovered');

    // 2. level 3 via a click on the bar button (selectRay -> ask bar -> /api/ask), duct run lights up
    await page.evaluate(([x, y]) => xrDebug.pickNdc(x, y), ndc3);
    await page.waitForFunction(() => ['answer', 'error'].includes(xrInspection().ask.phase), null, {timeout: 120000});
    st = await page.evaluate(() => xrInspection().ask);
    assert.equal(st.phase, 'answer', st.error || '');
    assert.equal(st.level, 3); assert.equal(st.bar, null, 'a preset folds the panel away'); assert.equal(st.chipVisible, false, 'only the answer card shows');
    assert.ok(st.run && st.run.pieces >= 3, 'connected_run path lit');
    assert.ok(st.glow.some(g => g.id === st.primary), 'primary citation glows');
    assert.ok(st.citations.every(c => c.verified));
    // waiting state (2026-11-15): step lines from the stream events, all ticked once the answer is in; the mark settled; the asked
    // element's pulsing wait glow replaced by the cited colours; the mark on its own small texture
    assert.ok(st.wait.steps.length >= 1 && st.wait.steps.every(x => x.state === 'done'), 'steps from the tool events, all done');
    assert.ok(st.wait.steps.some(x => x.icon === 'route'), 'connected_run step with the route pictogram');
    assert.equal(st.wait.settled, true); assert.equal(st.wait.dots, false); assert.ok(!st.glow.some(g => g.kind === 'wait'), 'wait pulse removed');
    assert.ok(st.tex.mark && st.tex.mark.w <= 512, 'small mark texture');
    report.level3 = {ms: st.answerMs, lead: st.lead, primary: st.primary, run: st.run, glow: st.glow.length, speechPlan: st.speechPlan};
    // turn the desktop view a little (right, down) so the card, the bar and the lit run are all in frame; everything is world-locked
    const frame = l => page.evaluate(({yaw, pitch}) => xrDebug.look(yaw - .12, pitch - .16), l);
    await frame(pick.look);
    await page.waitForTimeout(2600);   // run lit piece by piece, then the pulse
    await page.evaluate(() => xrDebug.renderNow());
    await shot('02-level3-what-feeds-it.png', 'level 3: answer card + duct run lit from the cited VAV box to the diffuser (inferred)');

    // 3. level 4 (reasoning across sources) and level 2
    for (const [lvl, name] of [[4, '03-level4-why-warm.png'], [2, '04-level2-whats-above.png']]) {
      const p2 = await page.evaluate(id => xrDebug.ask.pickId(id), DIFFUSER);
      await page.evaluate(l => xrDebug.ask.question(l), lvl);
      await frame(p2.look);
      st = await page.evaluate(() => xrInspection().ask);
      assert.equal(st.phase, 'answer', st.error || '');
      report['level' + lvl] = {ms: st.answerMs, lead: st.lead, primary: st.primary, run: st.run, glow: st.glow.length, steps: st.steps.length};
      await page.waitForTimeout(2200);
      await shot(name, 'level ' + lvl);
    }
    await page.waitForTimeout(500);
    report.speech = await page.evaluate(() => { const a = xrInspection().ask; return {plan: a.speechPlan, engine: a.speechEngine, state: a.speech, voices: speechSynthesis.getVoices().length}; });
    // close clears everything
    await page.evaluate(() => xrDebug.ask.button(5));
    st = await page.evaluate(() => xrInspection().ask);
    assert.equal(st.bar, null); assert.equal(st.glow.length, 0); assert.equal(st.cardVisible, false);

    // 4. stand-in controller (desktop preview only): controller 1's own ray + reticle onto the element, trigger -> pick;
    //    "⋯" -> presets; onto a preset button -> that button is hovered (nothing pressed); null hides it
    const sim = await page.evaluate(id => xrDebug.ask.simController({id}, {trigger: true}), DIFFUSER);
    assert.equal(sim?.kind, 'element'); assert.equal(sim.hitId, DIFFUSER); assert.equal(sim.picked?.id, DIFFUSER);
    st = await page.evaluate(() => xrInspection().ask);
    assert.equal(st.el.id, DIFFUSER); assert.equal(st.bar, null); assert.equal(st.chipVisible, true);
    assert.equal((await page.evaluate(() => xrDebug.ask.simController({button: 'more'}, {trigger: true}))).pressed, 'more');
    const simBtn = await page.evaluate(() => xrDebug.ask.simController({button: 0}));
    assert.equal(simBtn?.kind, 'button'); assert.equal(simBtn.button, 0); assert.equal(simBtn.pressed, undefined);
    st = await page.evaluate(() => xrInspection().ask);
    assert.equal(st.phase, null, 'hover alone asks nothing');
    await page.waitForTimeout(200);
    await shot('05-sim-controller-on-button.png', 'stand-in controller ray + reticle on button 1 (desktop preview only)');
    // slide mode (debug, default off): no listening ring while recording
    assert.deepEqual((await page.evaluate(() => xrDebug.ask.slideMode({ring: false}))).hideRing, true);
    // the trigger held on the label (controller selectstart / selectend): records about the picked element, release stops (fake microphone)
    if ((await page.evaluate(() => xrInspection().ask.voice)) === 'ready') {
      await page.evaluate(() => xrDebug.ask.simController({button: 'chip'}, {press: 'down'}));
      await page.waitForFunction(() => xrInspection().ask.voice === 'recording', null, {timeout: 10000});
      assert.equal(await page.evaluate(() => xrInspection().ask.ring), false, 'slide mode hides the listening ring');
      await page.waitForTimeout(1200);
      await page.evaluate(() => xrDebug.ask.simController({button: 'chip'}, {press: 'up'}));
      await page.waitForFunction(() => xrInspection().ask.voice !== 'recording', null, {timeout: 10000});
      report.simHold = 'recorded and released';
    } else report.simHold = 'skipped: voice not ready (server without speech-to-text)';
    await page.waitForFunction(() => !['transcribing'].includes(xrInspection().ask.voice) && !xrInspection().ask.busy, null, {timeout: 60000});
    assert.deepEqual(await page.evaluate(() => xrDebug.ask.simController(null)), {hidden: true});
    assert.equal((await page.evaluate(() => xrDebug.ask.slideMode())).hideRing, false, 'slide mode off again');
    report.simController = {element: {hitId: sim.hitId, distance: sim.distance}, button: simBtn.button};
    // B/Y (the back action) dismisses the pick: no Close button needed
    await page.evaluate(id => xrDebug.ask.simController({id}, {trigger: true}), DIFFUSER);
    assert.equal(await page.evaluate(() => xrDebug.ask.back()), 'dismiss');
    st = await page.evaluate(() => xrInspection().ask);
    assert.equal(st.el, null); assert.equal(st.chipVisible, false);
    assert.equal(await page.evaluate(() => xrInspection().ask.speechPlan || 'none'), 'none', 'silent');
    assert.deepEqual(errors, []);
    report.ok = true;
  } catch (e) { report.ok = false; report.error = String(e.stack || e); report.errors = errors; process.exitCode = 1; }
  finally { fs.writeFileSync(path.join(OUT, 'xr-ask-smoke.json'), JSON.stringify(report, null, 1)); console.log(JSON.stringify(report, null, 1)); await browser.close(); }
})();
