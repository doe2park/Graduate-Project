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
  assert.match(page, /<script src="twin\/xr-ask\.js\?v=8"><\/script>/);
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
  assert.ok(after.every(a => a >= 0.5), 'a lit piece stays solid between pulses');
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
test('canvas drawing: answer card (thinking / answer / error) and bar draw without throwing; small AI mark (no chat header) + cited ids + footer', () => {
  const m = XA.cardModel({question: 'Which VAV box feeds this?', answer: ANSWER, final: FINAL, level: 3});
  for (const view of [{phase: 'thinking', model: {question: 'q', level: 3}, steps: ['connected_run · 250 touching elements']}, {phase: 'answer', model: m, speech: 'speaking', runNote: 'Lit run: 11 pieces'}, {phase: 'error', model: {}, error: 'server 404'}]) {
    const ctx = fakeCtx(); XA.drawAnswer(ctx, 1024, 800, view);
    assert.ok(ctx.calls.includes('AI answer'), view.phase); assert.ok(!ctx.calls.includes('Claude'), view.phase);
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
  // the temporary public address (scripts/ask_twin_public.sh): exactly <words>.trycloudflare.com on 443, nothing that only looks like it
  assert.equal(XA.serverOrigin('https://tutorial-fairly-origins-brilliant.trycloudflare.com'), 'https://tutorial-fairly-origins-brilliant.trycloudflare.com');
  assert.equal(XA.serverOrigin('https://Two-Words.trycloudflare.com/'), 'https://two-words.trycloudflare.com');
  for (const raw of ['http://a-b.trycloudflare.com', 'https://trycloudflare.com', 'https://a.trycloudflare.com', 'https://a-b.trycloudflare.com.evil.example',
    'https://a-b.trycloudflare.com:8443', 'https://a-b.trycloudflare.com/api', 'https://x.a-b.trycloudflare.com', 'https://a_b-c.trycloudflare.com',
    'https://user@a-b.trycloudflare.com', 'https://a-b.cloudflare.com']) assert.equal(XA.serverOrigin(raw), null, raw);
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

test('plain live answers: the paragraph is the lead, the first Evidence id is the primary, chips use plain labels', () => {
  const plain = 'The air comes from a VAV box about 3 m away, above the ceiling. The model suggests this from touching ducts, so check the drawings.\nEvidence: [[400766]] [[388279]]';
  const S = XA.sections(plain);
  assert.equal(S.lead, plain.split('\n')[0]);
  assert.equal(XA.leadId(plain), '400766');
  const m = XA.cardModel({question: 'Where does the air come from?', answer: plain,
    final: {mode: 'live', model: 'claude-sonnet-5-5', tools_used: [{}], citations: [
      {id: '400766', known: true, verified: true, type: 'Terminal unit', label: 'VAV box'}, {id: '388279', known: true, verified: true, type: 'M-HVAC-CDFF', label: 'diffuser'}]}});
  assert.equal(m.primary, '400766');
  assert.deepEqual(m.chips.map(c => c.label), ['VAV box', 'diffuser']);
  assert.equal(m.confidence, null);
  assert.doesNotMatch(m.lead, /Evidence|\[\[/);
  assert.equal(XA.sections('Let me check.\n**Answer:** [[1]] x').lead, '[[1]] x');   // a header lead replaces a preamble line
});

/* Nov 9 visual card: structured tool visuals (scripts/ask_twin/agent.py tool_visual) -> headline + picture, no prose parsing for the graphics */
const Q1 = 'This is a supply air vent (a square perforated ceiling diffuser, about 0.6 m across) that blows air into the room from the ceiling on Level 1. You are probably in the Exhibit/Open Work Space 100-1. The twin has no room outlines, and the closest labelled item is in Storage B114A, about 5 m away, so check the room sign.\nEvidence: [[388189]] [[160879]]';
const Q1C = [{id: '388189', known: true, verified: true, layer: 'duct', type: 'M-HVAC-CDFF', label: 'diffuser', size_m: [0.6, 0.05, 0.6], level: 'L1'}, {id: '160879', known: true, verified: true, layer: 'equipment', type: 'Panel', label: 'panel'}];
const Q2 = 'Directly above this light, the closest thing is a fire sprinkler main (a 3-inch pipe) about 0.16 m up. A concrete beam on the level above is next, about 0.42 m up. This comes from the model geometry only, so check on site.\nEvidence: [[278081]] [[131161]] [[411938]]';
const NEAR = {kind: 'near', above_only: true, radius_m: 2, total: 147, counts_by_layer: {duct: 100, hydronic: 22, fire: 13, structural: 11},
  items: [{id: '278081', label: 'sprinkler pipe', layer: 'fire', type: 'Pipe', vertical: 'above', vertical_gap_m: 0.16, horizontal_gap_m: 0},
    {id: '131161', label: 'beam', layer: 'structural', type: 'Structural Framing', vertical: 'above', vertical_gap_m: 0.42, horizontal_gap_m: 0},
    {id: '411938', label: 'pipe', layer: 'hydronic', type: 'Pipe', vertical: 'above', vertical_gap_m: 0.05, horizontal_gap_m: 0.62},
    {id: '500001', label: 'duct', layer: 'duct', type: 'Duct', vertical: 'above', vertical_gap_m: 0.9, horizontal_gap_m: 1.1}]};
test('pictograms and plain names from element type / layer / server label', () => {
  const P = XA.pictogram;
  assert.equal(P({label: 'diffuser', type: 'M-HVAC-CDFF', layer: 'duct'}), 'vent');
  assert.equal(P({label: 'VAV box', type: 'Terminal unit', layer: 'duct'}), 'vav');
  assert.equal(P({label: 'duct', layer: 'duct'}), 'duct');
  assert.equal(P({label: 'sprinkler pipe', layer: 'fire'}), 'sprinkler');
  assert.equal(P({label: 'pipe', layer: 'hydronic'}), 'pipe');
  assert.equal(P({label: 'light', layer: 'lighting'}), 'light');
  assert.equal(P({type: 'Structural Framing', layer: 'structural'}), 'beam');
  assert.equal(P({label: 'valve', layer: 'plumbing'}), 'valve');
  assert.equal(P({layer: 'ceilings-l1', label: 'ceiling'}), 'ceiling');
  assert.equal(P(null), 'box');
  assert.equal(XA.niceName({label: 'diffuser'}), 'Air vent (diffuser)');
  assert.equal(XA.niceName({label: 'element', type: 'M-HVAC-CDFF'}), 'Element');   // CAD codes never shown as a name
  assert.equal(XA.sizeText({size_m: [0.6, 0.05, 0.6]}), '0.6 × 0.6 m');
  assert.equal(XA.sizeText({size: '3"', size_m: [5, .1, .1]}), '3"');
  assert.equal(XA.sizeText({size_m: [6.2, .3, .3]}), '6.2 m long');
  assert.deepEqual(XA.roomChip({room: 'EXHIBIT/ OPEN WORK SPACE 100-1', confidence: 'low'}), {name: 'Exhibit / Open Work Space 100-1', dots: 1, word: 'Best guess', basis: 'guessed from nearby labels'});
  assert.equal(XA.roomChip({room: 'B114A', confidence: 'medium'}).word, 'Probably');
  assert.equal(XA.roomChip({room: 'B114A', confidence: 'recorded'}).dots, 3);
  assert.equal(XA.roomChip({room: null}), null);
});
test('caption = first sentences without ids; check chip from the answer, else a per-kind default', () => {
  assert.equal(XA.captionText(Q2, 1), 'Directly above this light, the closest thing is a fire sprinkler main (a 3-inch pipe) about 0.16 m up.');
  assert.doesNotMatch(XA.captionText(Q1, 3), /Evidence|\[\[/);
  assert.equal(XA.checkText(Q1, 'lookup'), 'Check the room sign');
  assert.equal(XA.checkText(Q2, 'near'), 'Check on site');
  assert.equal(XA.checkText('The duct link comes from touching shapes, so check the duct drawings or the BAS (building automation system) points on site.', 'trace'), 'Check the duct drawings or the BAS points on site');
  assert.equal(XA.checkText('No hint here.', 'near'), 'Look above the ceiling tile on site');
});
test('visual: look up -> element pictogram, size, level, room chip with how sure', () => {
  const v = XA.answerVisual({visuals: [{kind: 'room', room: 'EXHIBIT/ OPEN WORK SPACE 100-1', level: 'L1', confidence: 'low', basis: 'nearby labels'}], citations: Q1C, primary: '388189',
    selected: {id: '388189', layer: 'duct', type: 'M-HVAC-CDFF'}, answer: Q1});
  assert.equal(v.kind, 'lookup'); assert.equal(v.headline, 'Air vent (diffuser)'); assert.equal(v.element.picto, 'vent');
  assert.equal(v.size, '0.6 × 0.6 m'); assert.equal(v.level, 'Level 1'); assert.equal(v.room.word, 'Best guess'); assert.equal(v.check, 'Check the room sign');
  assert.ok(v.caption.startsWith('This is a supply air vent'));
});
test('visual: nearby -> height markers (cited first, at their gaps), counts by system, headline from the closest item above', () => {
  const cites = ['278081', '131161', '411938'].map(id => ({id, known: true, verified: true}));
  const v = XA.answerVisual({visuals: [NEAR], citations: cites, primary: '278081', selected: {id: '23006', layer: 'lighting'}, answer: Q2});
  assert.equal(v.kind, 'near'); assert.equal(v.self.picto, 'light');
  assert.deepEqual(v.marks.map(m => [m.id, m.picto, m.dy, m.cited]), [['278081', 'sprinkler', .16, true], ['131161', 'beam', .42, true], ['411938', 'pipe', .05, true], ['500001', 'duct', .9, false]]);
  assert.equal(v.headline, 'Sprinkler pipe 0.16 m above');   // closest directly above (the copper pipe is 0.62 m aside)
  assert.deepEqual(v.counts.map(c => [c.layer, c.n, c.picto]), [['duct', 100, 'duct'], ['hydronic', 22, 'pipe'], ['fire', 13, 'sprinkler'], ['structural', 11, 'beam']]);
});
test('visual: trace -> this element, pieces along the run, the cited source with its distance', () => {
  const run = {kind: 'run', layer: 'duct', reached: 150, start: {id: '388219', label: 'diffuser', layer: 'duct'},
    notable: [{id: '400766', label: 'VAV box', type: 'Terminal unit', layer: 'duct', hops: 12, horizontal_gap_m: 3.4, vertical: 'above'}]};
  const v = XA.answerVisual({visuals: [run], citations: [{id: '400766', known: true, verified: true}, {id: '388219', known: true, verified: true}], primary: '400766',
    selected: {id: '388219', layer: 'duct'}, answer: 'The air probably comes from a VAV box. Check the duct drawings.'});
  assert.equal(v.kind, 'trace'); assert.equal(v.headline, 'Probably fed by a VAV box');
  assert.deepEqual([v.from.picto, v.to.picto, v.hops, v.away, v.where, v.pieceWord], ['vent', 'vav', 12, 3.4, 'above the ceiling', 'duct pieces']);
});
test('visual: the headline never names something the answer did not cite', () => {
  const run = {kind: 'run', layer: 'duct', reached: 40, start: {id: '388219', label: 'diffuser', layer: 'duct'},
    notable: [{id: '400766', label: 'VAV box', type: 'Terminal unit', layer: 'duct', hops: 12, horizontal_gap_m: 3.4, vertical: 'above'}]};
  // "What is this?" answered from the element alone: an uncited run visual does not turn it into "Probably fed by ..."
  const what = XA.answerVisual({visuals: [run], citations: [{id: '388219', known: true, verified: true, label: 'diffuser', layer: 'duct'}], primary: '388219',
    selected: {id: '388219', layer: 'duct'}, answer: 'This is a ceiling diffuser. Check on site.'});
  assert.notEqual(what.kind, 'trace'); assert.doesNotMatch(what.headline, /fed by/i);
  // a cited-but-unverified id does not count either
  assert.notEqual(XA.answerVisual({visuals: [run], citations: [{id: '400766', known: true, verified: false}], primary: '400766', selected: {id: '388219', layer: 'duct'}, answer: 'x.'}).kind, 'trace');
  // a pipe run is not "fed by"
  const pipe = XA.answerVisual({visuals: [{kind: 'run', layer: 'plumbing', reached: 9, start: {id: '5', label: 'pipe', layer: 'plumbing'}, notable: [{id: '6', label: 'valve', layer: 'plumbing', hops: 3}]}],
    citations: [{id: '6', known: true, verified: true}], primary: '6', selected: {id: '5', layer: 'plumbing'}, answer: 'The nearest shut-off is a valve. Check on site.'});
  assert.equal(pipe.kind, 'trace'); assert.equal(pipe.headline, 'Connected to a valve');
  // near: the closest thing above is an uncited sprinkler pipe, but the answer cited the duct
  const near = {kind: 'near', above_only: true, total: 2, radius_m: 2, counts_by_layer: {duct: 1, fire: 1}, items: [
    {id: 'p1', label: 'sprinkler pipe', layer: 'fire', vertical: 'above', vertical_gap_m: .2, horizontal_gap_m: 0},
    {id: 'd1', label: 'duct', layer: 'duct', vertical: 'above', vertical_gap_m: .9, horizontal_gap_m: .1}]};
  const cited = XA.answerVisual({visuals: [near], citations: [{id: 'd1', known: true, verified: true}], primary: 'd1', selected: {id: 't1', layer: 'ceilings'}, answer: 'A duct runs about 0.9 m above.'});
  assert.match(cited.headline, /^Duct 0\.9\d* m above$/);
  const none = XA.answerVisual({visuals: [near], citations: [], selected: {id: 't1', layer: 'ceilings'}, answer: 'Several things are above.'});
  assert.match(none.headline, /^Sprinkler pipe 0\.2\d* m above$/);   // nothing cited above: the closest neighbour, as before
});
test('visual: other questions -> first sentence headline + cited element tiles; no visuals -> text card as before', () => {
  const v = XA.answerVisual({visuals: [], citations: [{id: '9', known: true, verified: true, label: 'pipe', layer: 'plumbing'}], answer: 'A simulated demo sensor reads warm. Check the valve.'});
  assert.equal(v.kind, 'text'); assert.equal(v.headline, 'A simulated demo sensor reads warm.'); assert.equal(v.items[0].picto, 'pipe');
  assert.equal(XA.cardModel({answer: ANSWER, final: FINAL}).visual, null);
});
test('visual cards draw without throwing for every kind, with headline, check chip, ids and the honesty footer', () => {
  const cites = ['278081', '131161', '411938'].map(id => ({id, known: true, verified: true, label: 'x'}));
  const cases = [
    XA.cardModel({question: 'q', answer: Q1, final: {mode: 'live', model: 'm', citations: Q1C, tools_used: [{}]}, visuals: [{kind: 'room', room: 'B114A', level: 'L1', confidence: 'low'}], selected: {id: '388189', layer: 'duct'}}),
    XA.cardModel({question: 'q', answer: Q2, final: {mode: 'live', model: 'm', citations: cites, tools_used: [{}]}, visuals: [NEAR], selected: {id: '23006', layer: 'lighting'}}),
    XA.cardModel({question: 'q', answer: ANSWER, final: FINAL, visuals: [{kind: 'run', layer: 'duct', start: {id: '388279', label: 'diffuser'}, notable: [{id: '400766', label: 'VAV box', hops: 11, horizontal_gap_m: 3.1, vertical: 'above'}]}], selected: {id: '388279', layer: 'duct'}}),
    XA.cardModel({question: 'q', answer: 'Short. Check the valve.\nEvidence: [[9]]', final: {mode: 'mock', citations: [{id: '9', known: true, verified: true, label: 'pipe', layer: 'plumbing'}], tools_used: []}, visuals: []})];
  for (const m of cases) {
    const ctx = fakeCtx(); XA.drawAnswer(ctx, 1024, 800, {phase: 'answer', model: m, speech: 'text only'});
    assert.ok(ctx.calls.includes(m.visual.headline), m.visual.kind); assert.ok(ctx.calls.some(t => t.includes(m.visual.check)), m.visual.kind);
    assert.ok(ctx.calls.some(t => /^#\d/.test(t)), m.visual.kind); assert.ok(ctx.calls.some(t => /SIMULATED/.test(t)), m.visual.kind);
    assert.ok(!ctx.calls.some(t => /Claude/.test(t)) || m.mode === 'live', m.visual.kind);
  }
  assert.ok(page.includes('if(ev.visual&&typeof ev.visual===\'object\')ASK.vis.push(ev.visual);'));
  assert.ok(page.includes('visuals:ASK.vis,selected:'));
});

test('connect with the code only: the announced address must have the temporary-address form; the code is cleaned, never looked up', () => {
  const now = Date.parse('2026-11-13T20:00:00Z'), T = 'https://calm-river-two-words.trycloudflare.com';
  assert.deepEqual(XA.endpointFrom({server: T, updated: '2026-11-13T19:00:00Z'}, now), {ok: true, server: T, ageH: 1, stale: false});
  assert.equal(XA.endpointFrom({server: T + '/', updated: '2026-11-12T00:00:00Z'}, now).stale, true);
  assert.equal(XA.endpointFrom({server: T}, now).ageH, null);
  for (const bad of [null, {}, {server: null}, {server: 'https://evil.example'}, {server: 'https://192.168.1.2:8765'}, {server: 'https://localhost:8765'},
    {server: 'http://calm-river.trycloudflare.com'}, {server: T + '/x'}, {server: 'https://a-b.trycloudflare.com.evil.example'}, 'text', 7])
    assert.equal(XA.endpointFrom(bad, now).ok, false, JSON.stringify(bad));
  assert.equal(XA.connectCode(' q47-hwc '), 'Q47HWC'); assert.equal(XA.connectCode('abc'), null); assert.equal(XA.connectCode(''), null); assert.equal(XA.connectCode(null), null);
  assert.ok(XA.ENDPOINT.api.startsWith('https://api.github.com/repos/doe2park/Graduate-Project/') && XA.ENDPOINT.raw.includes('/ask-endpoint/ask-endpoint.json'));
  assert.ok(!/code/i.test(JSON.stringify(XA.ENDPOINT)), 'the endpoint file never carries the access code');
});
