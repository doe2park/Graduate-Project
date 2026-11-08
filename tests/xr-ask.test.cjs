/* twin/xr-ask.js: the headset "Ask the twin" helpers (scan-xr.html?ask=1). Pure logic + canvas drawing against a recording context.
   node --test tests/xr-ask.test.cjs */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const XA = require('../twin/xr-ask.js');
const page = fs.readFileSync(path.join(__dirname, '..', 'scan-xr.html'), 'utf8');

// A real mock answer shape (scripts/ask_twin/agent.py MockAgent._feed for diffuser 388279), citations as the server returns them.
const ANSWER = `**Answer:** Nearest air source on this run: [[400766]] air terminal with hot-water reheat coil, 11 steps along touching ducts from [[388279]] · confidence: low
**Why:**
- Touching-box run of 250 duct elements (Duct 194, Duct tap 14, Rectangular duct 13).
- inferred from Price SDV/coil family name.
**Check first:**
- Trace the duct from [[388279]] to [[400766]] on the mechanical drawings.
**Other candidates:**
- [[400767]] Terminal unit - air terminal with hot-water reheat coil, 10 segments
**Limits:** touching boxes are not verified connections; no airflow direction in the model. *(mock mode: scripted, tool-grounded)*`;
const CITES = [
  {id: '400766', known: true, verified: true, layer: 'duct', type: 'Terminal unit', bbox_m: [0, 0, 0, 1, 1, 1]},
  {id: '388279', known: true, verified: true, layer: 'duct', type: 'M-HVAC-CDFF', bbox_m: [0, 0, 0, 1, 1, 1]},
  {id: '400767', known: true, verified: true, layer: 'duct', type: 'Terminal unit', bbox_m: [0, 0, 0, 1, 1, 1]},
  {id: '999999', known: true, verified: false, layer: 'duct', type: 'Duct', bbox_m: [0, 0, 0, 1, 1, 1]}];
const FINAL = {type: 'final', answer: ANSWER, citations: CITES, tools_used: [{name: 'connected_run'}], mode: 'mock', model: 'mock (scripted, tool-grounded)'};

test('inert unless ?ask=1', () => {
  assert.equal(XA.parseParams('').enabled, false);
  assert.equal(XA.parseParams('?mode=ar&ask=0').enabled, false);
  assert.equal(XA.parseParams('?mode=ar&place=demo&ask=1').enabled, true);
});

test('page loads the versioned helper and checks its API before turning on', () => {
  assert.match(page, /<script src="twin\/xr-ask\.js\?v=3"><\/script>/);
  assert.match(page, new RegExp(`XA\\?\\.API===${XA.API}`));
  assert.match(page, /XAP=XAOK\?XA\.parseParams\(location\.search\):\{enabled:false\}/);
  assert.match(page, /ASK=\{on:!!XAP\.enabled,base:XAP\.server\|\|null/);
  // the hold-to-ask hook in the trigger handler is guarded too
  assert.ok(page.includes('function onSelect(c){const u=c.userData;if(ASK?.on&&askHoldSwallow(c))return;'));
  // every API call goes through askApi (same origin, or the validated laptop origin)
  assert.doesNotMatch(page, /fetch\('api\//);
  // every hook into the existing page is guarded, so the page is unchanged without ?ask=1
  for (const hook of ['if(ASK?.on)askOnPick', 'function hideCard(){if(ASK?.on)askClear();', 'if(ASK?.on)try{askAnim=askTick();}']) assert.ok(page.includes(hook), hook);
  assert.match(page, /function askPanelHit\(o,d\)\{if\(!ASK\?\.on\|\|!askBar\.mesh\.visible\)return null;/);
});

test('SSE stream: events split across arbitrary chunks', () => {
  const evs = [], s = XA.createStream(e => evs.push(e));
  const raw = 'data: {"type":"tool","name":"get_element"}\n\ndata: {"type":"text","text":"Hi "}\n\ndata: {"type":"final","answer":"Hi"}\n\n';
  for (let i = 0; i < raw.length; i += 7) s.push(raw.slice(i, i + 7));
  s.end();
  assert.deepEqual(evs.map(e => e.type), ['tool', 'text', 'final']);
  const bad = []; XA.createStream(e => bad.push(e)).push('data: {oops\n\n');
  assert.equal(bad[0].type, 'error');
});

test('card model: short lead, 2 evidence bullets + first check, verified chips first, provenance footer', () => {
  const m = XA.cardModel({question: 'Which VAV box feeds this?', answer: ANSWER, final: FINAL, level: 3});
  assert.equal(m.primary, '400766');
  assert.equal(m.confidence, 'low');
  assert.match(m.lead, /^Nearest air source on this run: #400766 air terminal/);
  assert.doesNotMatch(m.lead, /\[\[|\*\*|confidence/);
  assert.deepEqual(m.bullets.map(b => b.kind), ['why', 'why', 'check']);
  assert.match(m.bullets[2].text, /^Trace the duct from #388279 to #400766/);
  assert.equal(m.chips[0].id, '400766'); assert.equal(m.chips[0].primary, true);
  assert.equal(m.chips.at(-1).verified, false);
  assert.match(m.limits, /not verified connections/); assert.doesNotMatch(m.limits, /mock mode/);
  assert.match(m.footer[0], /^MOCK · scripted from real tool results · 1 lookups · 3\/4 cited IDs verified$/);
  assert.match(m.footer[1], /SIMULATED/); assert.match(m.footer[1], /not headset-verified/);
  // an unverified lead id is never the highlighted primary
  const f2 = {...FINAL, citations: CITES.map(c => c.id === '400766' ? {...c, verified: false} : c)};
  assert.equal(XA.cardModel({answer: ANSWER, final: f2}).primary, null);
});

test('spoken text (fallback): lead + one check only, element types instead of ids, no markdown, no confidence, no Limits', () => {
  const t = XA.speakable(ANSWER, CITES);
  assert.doesNotMatch(t, /\[\[|\*|400766|388279|Limits|mock|onfidence|Touching-box|Other/);
  assert.match(t, /Terminal unit/); assert.match(t, /First, trace the duct/);
  assert.ok(t.split(/[.!?](\s|$)/).filter(x => x && x.trim()).length <= 2, t);
  assert.match(XA.speakable('**Answer:** Closest: [[1]] pipe, ~1.1 m above.', [{id: '1', type: 'Pipe'}]), /about 1\.1 metres above/);
});

test('run path: the connected_run path to the cited source, lit from the source to the picked element', () => {
  const paths = [{to: '400767', ids: ['388279', 'a', '400767']}, {to: '400766', ids: ['388279', 'b', 'c', '400766']}];
  assert.deepEqual(XA.runPath(paths, '400766', CITES), ['400766', 'c', 'b', '388279']);
  assert.deepEqual(XA.runPath(paths, 'nope', CITES), ['400767', 'a', '388279']);   // falls back to any verified end
  assert.equal(XA.runPath(paths, '400766', []), null);   // nothing verified -> nothing lit
  assert.equal(XA.runPath([], '400766', CITES), null);
});

test('run glow: dark before its turn, lit in order, a pulse afterwards; reduced motion = steady', () => {
  assert.equal(XA.runGlow(3, 10, 200), 0);
  assert.ok(XA.runGlow(0, 10, 200) > 0);
  assert.ok(XA.runGlow(0, 10, 2000) >= 0.3);
  const after = Array.from({length: 10}, (_, i) => XA.runGlow(i, 10, 10 * 90 + 600));
  assert.ok(Math.max(...after) > Math.min(...after) + 0.1, 'a pulse travels along the run');
  assert.ok(after.every(a => a <= 0.8));
  assert.equal(XA.runGlow(5, 10, 0, {reduced: true}), 0.5);
});

test('ask bar: six buttons, plane-UV hit test (v up), gaps miss', () => {
  const rects = XA.barRects(), btn = XA.barButtons({voice: 'ready'});
  assert.equal(rects.length, btn.length);
  assert.deepEqual(btn.map(b => b.id), ['q1', 'q2', 'q3', 'q4', 'mic', 'close']);
  rects.forEach((r, i) => assert.equal(XA.barHit(r.x + r.w / 2, 1 - (r.y + r.h / 2)), i));
  assert.equal(XA.barHit(.005, .5), -1);
  assert.equal(XA.barHit(rects[0].x + rects[0].w + XA.BAR.gap / 2, 1 - (rects[0].y + rects[0].h / 2)), -1);
  assert.deepEqual(XA.LEVELS.map(l => l.level), [1, 2, 3, 4]);
  assert.equal(XA.barButtons({voice: 'off'})[4].disabled, true);
  assert.equal(XA.barButtons({voice: 'recording', busy: false})[4].label, 'Listening… release');
  assert.equal(XA.barButtons({busy: true})[0].disabled, true);
});

test('voice plans: mic opened before the session, laptop voice when the browser has none', () => {
  const ok = {secure: true, getUserMedia: true, mediaRecorder: true, stt: true};
  assert.equal(XA.micPlan({...ok, haveStream: true}).mode, 'ready');
  assert.equal(XA.micPlan(ok).mode, 'ask');
  assert.equal(XA.micPlan({...ok, presenting: true}).mode, 'try');
  assert.equal(XA.micPlan({...ok, secure: false}).mode, 'off');
  assert.equal(XA.micPlan({...ok, stt: false}).mode, 'off');
  assert.equal(XA.ttsPlan({synth: true, voices: 3, server: true}), 'server');            // laptop voice preferred
  assert.equal(XA.ttsPlan({synth: true, voices: 3, server: true, prefer: 'browser'}), 'browser');
  assert.equal(XA.ttsPlan({synth: true, voices: 3, server: false}), 'browser');
  assert.equal(XA.ttsPlan({synth: true, voices: 0, server: true}), 'server');
  assert.equal(XA.ttsPlan({synth: true, voices: 0, server: false}), 'browser-unknown');
  assert.equal(XA.ttsPlan({synth: false, server: false}), 'none');
});

function fakeCtx() {
  const calls = [];
  return new Proxy({calls, measureText: t => ({width: String(t).length * 14}), fillText: t => calls.push(String(t))}, {
    get: (o, k) => k in o ? o[k] : (k === 'roundRect' ? () => {} : typeof k === 'string' && /^[a-z]/.test(k) && !['font', 'fillStyle', 'strokeStyle', 'lineWidth', 'textAlign', 'lineCap', 'lineJoin'].includes(k) ? () => {} : o[k]),
    set: (o, k, v) => { o[k] = v; return true; }});
}
test('canvas drawing: answer card (thinking / answer / error) and bar draw without throwing; badge + cited ids + footer', () => {
  const m = XA.cardModel({question: 'Which VAV box feeds this?', answer: ANSWER, final: FINAL, level: 3});
  for (const view of [{phase: 'thinking', model: {question: 'q', level: 3}, steps: ['connected_run · 250 touching elements']}, {phase: 'answer', model: m, speech: 'speaking', runNote: 'Lit run: 11 pieces'}, {phase: 'error', model: {}, error: 'server 404'}]) {
    const ctx = fakeCtx(); XA.drawAnswer(ctx, 1024, 800, view);
    assert.ok(ctx.calls.includes('Claude'), view.phase);
    if (view.phase === 'answer') { assert.ok(ctx.calls.some(t => t.startsWith('#400766'))); assert.ok(ctx.calls.includes('READ ALOUD')); assert.ok(ctx.calls.some(t => /SIMULATED/.test(t))); }
    if (view.phase === 'thinking') assert.ok(ctx.calls.some(t => /connected_run/.test(t)));
    if (view.phase === 'error') assert.ok(ctx.calls.includes('Could not answer'));
  }
  const ctx = fakeCtx(); XA.drawBar(ctx, 1024, 300, XA.barButtons({voice: 'ready'}), new Set([1]));
  assert.ok(ctx.calls.includes('1 · What is this?') && ctx.calls.includes('Hold to speak'));
});

test('server= (Method A): https + private LAN IPv4 or localhost + explicit port, else ignored', () => {
  const ok = {'https://192.168.68.52:8765': 'https://192.168.68.52:8765', 'https://10.0.0.5:8765/': 'https://10.0.0.5:8765',
    'https://172.16.0.1:9000': 'https://172.16.0.1:9000', 'https://172.31.255.254:8765': 'https://172.31.255.254:8765',
    'https://localhost:8765': 'https://localhost:8765', 'HTTPS://192.168.1.2:8765': 'https://192.168.1.2:8765'};
  for (const [raw, want] of Object.entries(ok)) assert.equal(XA.serverOrigin(raw), want, raw);
  for (const raw of ['http://192.168.68.52:8765', 'https://192.168.68.52', 'https://192.168.68.52:443', 'https://8.8.8.8:8765',
    'https://172.32.0.1:8765', 'https://172.15.0.1:8765', 'https://192.169.1.1:8765', 'https://evil.example:8765', 'https://doe2park.github.io:8765',
    'https://192.168.1.2.nip.io:8765', 'https://user:pw@192.168.1.2:8765', 'https://192.168.1.2:8765/api', 'https://192.168.1.2:8765?x=1',
    'https://192.168.1.2:8765#a', 'https://[::1]:8765', 'https://0x7f.0.0.1:8765', 'https://192.168.001.2:8765', 'https://256.168.1.2:8765',
    'javascript:alert(1)', '//192.168.1.2:8765', '', ' ']) assert.equal(XA.serverOrigin(raw), null, raw);
  const p = XA.parseParams('?mode=ar&ask=1&server=https://192.168.68.52:8765');
  assert.deepEqual([p.enabled, p.server, p.serverIgnored], [true, 'https://192.168.68.52:8765', false]);
  const bad = XA.parseParams('?ask=1&server=https://evil.example:8765');
  assert.deepEqual([bad.server, bad.serverIgnored], [null, true]);
  assert.equal(XA.parseParams('?ask=1').server, null);
  assert.equal(XA.parseParams('?ask=1&voice=headset').preferVoice, 'browser');
  assert.equal(XA.apiUrl(null, 'ask'), 'api/ask');
  assert.equal(XA.apiUrl('https://192.168.68.52:8765', 'health'), 'https://192.168.68.52:8765/api/health');
});

test('health problem: one-tap trust link only for the validated laptop origin', () => {
  const p = XA.healthProblem({server: 'https://192.168.68.52:8765', error: 'network or certificate'});
  assert.equal(p.trustUrl, 'https://192.168.68.52:8765/trust');
  assert.equal(p.trustLabel, 'Open https://192.168.68.52:8765/ once to trust it');
  assert.equal(XA.healthProblem({}).trustUrl, null);
  assert.match(XA.healthProblem({ignored: true}).text, /ignored/);
});

test('waiting feedback: progress lines from server events, earcons, hold-to-ask gate', () => {
  assert.equal(XA.progressText({type: 'status', phase: 'thinking', text: 'Thinking…'}), 'Thinking…');
  assert.equal(XA.progressText({type: 'status', text: 'retrying'}), null);
  assert.equal(XA.progressText({type: 'tool', name: 'connected_run', input: {}}, {layer: 'duct'}), 'Following the ducts…');
  assert.equal(XA.progressText({type: 'tool', name: 'elements_near', input: {above_only: true}}), 'Checking what is above it…');
  assert.equal(XA.progressText({type: 'tool', name: 'sensor_readings', input: {}}), 'Reading the demo sensors (simulated)…');
  assert.equal(XA.progressText({type: 'text', text: 'x'}), 'Writing the answer…');
  for (const k of ['listen', 'send', 'done', 'miss']) assert.ok(XA.EARCONS[k].every(([f, t, d, g]) => f > 100 && d <= .2 && g <= .2), k);
  assert.ok(XA.HOLD_MS >= 250 && XA.HOLD_MS <= 600); assert.equal(XA.FILLER_MS, 1500);
  const base = {on: true, placed: true};
  assert.equal(XA.holdAskAllowed(base), true);
  for (const k of [{hoverPanel: 'ask'}, {aiming: true}, {grip: true}, {placing: true}, {placed: false}, {busy: true}, {on: false}])
    assert.equal(XA.holdAskAllowed({...base, ...k}), false, JSON.stringify(k));
  const ctx = fakeCtx(); XA.drawAnswer(ctx, 1024, 800, {phase: 'thinking', model: {question: 'q'}, progress: 'Following the ducts…', steps: []});
  assert.ok(ctx.calls.includes('Following the ducts…'));
});

test('access code (API 3): code= from the URL, X-Ask-Code on ask/transcribe/speak, friendly 401/429', () => {
  assert.equal(XA.API, 3);
  assert.equal(XA.parseParams('?ask=1&server=https://192.168.1.20:8765&code=ab23cd').code, 'AB23CD');
  assert.equal(XA.parseParams('?ask=1').code, '');
  assert.equal(XA.accessCode('?code=k7-px 3m'), 'K7PX3M');
  assert.deepEqual(XA.askHeaders('AB23CD', {'Content-Type': 'application/json'}), {'Content-Type': 'application/json', 'X-Ask-Code': 'AB23CD'});
  assert.deepEqual(XA.askHeaders('', {a: 1}), {a: 1});
  assert.match(XA.refusalText(401, {reason: 'code_required'}), /Access code needed/);
  assert.match(XA.refusalText(401, {reason: 'code_wrong'}), /Wrong access code/);
  assert.match(XA.refusalText(429, {error: 'Easy there: at most 10 questions per minute. Try again in 40 s.'}), /40 s/);
  assert.equal(XA.refusalText(404, {}), null);
  assert.match(page, /ASK=\{on:!!XAP\.enabled,base:XAP\.server\|\|null,code:XAP\.code\|\|''/);
  for (const name of ['ask', 'speak', 'transcribe']) assert.match(page, new RegExp(`fetch\\(askApi\\('${name}'\\),\\{method:'POST',headers:XA\\.askHeaders\\(ASK\\.code`), name);
  assert.match(page, /askRefusal\(res\)/);
});
