/* Public sensor deck (talks/sensor-deck/, served by GitHub Pages): every asset it references resolves inside the folder,
   live-view URLs are relative and opt-in (sensors=demo + a known scene), nothing private or local leaks in, every image
   has provenance and every lecture figure carries its course credit. Static checks only (no browser). */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const root = path.join(__dirname, '..'), deck = path.join(root, 'talks', 'sensor-deck');
const read = f => fs.readFileSync(path.join(deck, f), 'utf8');
const html = read('index.html'), sources = read('img/SOURCES.md');
const CFG = JSON.parse(fs.readFileSync(path.join(root, 'twin', 'sensors', 'registry.json'), 'utf8'));
const scenes = new Set(CFG.sensors.map(s => s.scenario));
const unesc = s => s.replace(/&amp;/g, '&');

test('every local asset referenced by index.html exists in the deck folder', () => {
  const refs = [...html.matchAll(/(?:src|href)="([^"#]+)"/g)].map(m => unesc(m[1])).filter(u => !/^(https?:|mailto:|data:)/.test(u));
  const fonts = [...html.matchAll(/url\(([^)#]+)\)/g)].map(m => m[1].replace(/['"]/g, ''));
  const local = [...refs, ...fonts].filter(u => !u.startsWith('../../'));
  assert.ok(local.length > 10);
  for (const u of local) assert.ok(fs.existsSync(path.join(deck, u.split('?')[0])), 'missing ' + u);
  for (const f of fs.readdirSync(path.join(deck, 'fonts')).filter(f => f.endsWith('.ttf'))) assert.ok(html.includes('fonts/' + f), 'font used: ' + f);
});

test('live views: relative viewer URL, sensors=demo, one known scene per concept slide, matching Open links', () => {
  const lives = [...html.matchAll(/data-src="([^"]+)"/g)].map(m => unesc(m[1]));
  assert.equal(lives.length, 5);
  const seen = [];
  for (const u of lives) {
    assert.match(u, /^\.\.\/\.\.\/scan-compare\.html\?/, 'relative to talks/sensor-deck/: ' + u);
    const q = new URLSearchParams(u.split('?')[1]);
    assert.equal(q.get('sensors'), 'demo'); assert.equal(q.get('capture'), '2026-05-06'); assert.equal(q.get('view'), 'overlay');
    assert.ok(scenes.has(q.get('scene')), 'known scene ' + q.get('scene'));
    assert.equal(q.get('focus'), CFG.primary[q.get('scene')], 'Lens opens on the scene primary');
    assert.equal(q.get('at').split(',').length, 8);
    assert.ok(html.includes('href="' + u.replace(/&/g, '&amp;') + '"'), 'Open in viewer link for ' + q.get('scene'));
    seen.push(q.get('scene'));
  }
  assert.deepEqual(seen, ['leak', 'air', 'water', 'elec', 'rotating']);
  for (const p of lives) assert.ok(fs.existsSync(path.join(deck, p.split('?')[0])), 'viewer resolves from the deck folder');
  assert.equal((html.match(/class="live twlive" data-live="sensor"/g) || []).length, 5, 'one live twin per concept slide');
  assert.match(html, /const keep=new Set\(\[slides\[i\],slides\[i\+1\]\]/, 'live views load on their slide and one slide ahead only');
});

test('nothing private, local-only or personal in the public folder', () => {
  const files = [];
  (function walk(d) { for (const f of fs.readdirSync(d)) { const p = path.join(d, f); if (fs.statSync(p).isDirectory()) walk(p); else files.push(p); } })(deck);
  const allowedDirs = ['', 'img', 'fonts'];
  for (const f of files) {
    const rel = path.relative(deck, f);
    assert.ok(allowedDirs.includes(path.dirname(rel) === '.' ? '' : path.dirname(rel)), 'unexpected folder: ' + rel);
    assert.ok(/\.(html|css|js|py|json|md|txt|ttf|jpg|png)$/.test(rel), 'unexpected file type: ' + rel);
    if (!/\.(ttf|jpg|png)$/.test(rel)) {
      const t = fs.readFileSync(f, 'utf8');
      // Oct 18 is named only for the two open-ceiling views the owner approved for public use (2026-10-27); see the image check below.
      for (const bad of [/2026-10-18/, /capture-local/, ...(rel === 'README.md' ? [] : [/127\.0\.0\.1|localhost/]), /@gmail\.com|@berkeley\.edu/, /ghp_[A-Za-z0-9]{10}|github_pat_/, /Chung/])
        assert.ok(!bad.test(t), rel + ' matches ' + bad);
    }
  }
  const OCT18_OK = ['oct18-ceiling-open-photo.jpg', 'oct18-ceiling-open-model.jpg'];
  for (const f of fs.readdirSync(path.join(deck, 'img')).filter(f => /oct.?18|10-?18/i.test(f))) assert.ok(OCT18_OK.includes(f), 'Oct 18 image not approved for public use: ' + f);
  assert.match(sources, /approved public use on 2026-10-27/);
  assert.match(html, /Concept mockup — no sensors are installed; values are illustrative\./);
  assert.ok(!/>Ask</.test(html) && html.includes('What we need'), 'slide 3 label is "What we need"');
});

test('provenance: every image is listed in img/SOURCES.md and used; lecture figures carry the course credit', () => {
  const imgs = fs.readdirSync(path.join(deck, 'img')).filter(f => /\.(jpg|png)$/.test(f));
  for (const f of imgs) {
    assert.ok(sources.includes(f), 'listed in SOURCES.md: ' + f);
    assert.ok(html.includes('img/' + f), 'used by the deck: ' + f);
  }
  for (const f of imgs.filter(f => f.startsWith('l24-'))) {
    const page = f.match(/^l24-p(\d+)-/)[1];
    assert.ok(html.includes('CE170/278 Infrastructure Sensing, UC Berkeley (Prof. K. Soga), Lecture 2-4, p. ' + page), 'credit for ' + f);
  }
  /* relevance (owner, 2026-10-25): no bridge / rail / gas-pipeline / telecom imagery; off-building projects only as a one-line lab track record */
  const visible = html.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<[^>]+>/g, ' ');
  for (const w of [/bridge/i, /\brail\b/i, /telecom/i, /gas pipeline/i, /Asurnipal|L2MRail|Lei et al\./]) assert.ok(!w.test(visible), 'off-topic content: ' + w);
  assert.equal((visible.match(/Lab track record/g) || []).length, 1, 'track record framed in one line');
  assert.match(html, /own CE278 final project/);
  assert.ok(fs.readFileSync(path.join(deck, 'fonts', 'OFL.txt'), 'utf8').includes('SIL OPEN FONT LICENSE Version 1.1'));
});

test('test-install slides: a callout card per sensor over the image, with simulated charts from the registry / feed', () => {
  const layers = [...html.matchAll(/<div class="twco" data-ob='([^']+)' style="left:([\d.]+)px;top:([\d.]+)px;width:([\d.]+)px;height:([\d.]+)px">/g)];
  const figs = [...html.matchAll(/<div class="tw" data-slug="[^"]+"[^>]*style="left:([\d.]+)px;top:([\d.]+)px;width:([\d.]+)px;height:([\d.]+)px">/g)].map(m => m.slice(1).map(Number));
  assert.equal(layers.length, 5); assert.equal(figs.length, 5);
  layers.forEach((m, i) => {
    assert.deepEqual(m.slice(2).map(Number), figs[i], 'callout layer covers exactly the image on concept slide ' + (i + 1));
    const ob = JSON.parse(m[1]);
    for (const [k, o] of Object.entries(ob)) { assert.equal(o.b.length, 3, 'badge x, y, r for marker ' + k); assert.ok(Array.isArray(o.geo) && Array.isArray(o.area)); }
  });
  assert.ok(!/class="twpanel|class="twinfo|class="twcard/.test(html), 'no duplicate details panel in the right column, no old popup');
  assert.ok(!/\.slide\.tw-sel \.twsteps\{display:none\}/.test(html), 'the steps stay visible while a sensor is selected');
  const charts = html.match(/<svg class="twc"/g) || [];
  assert.ok(charts.length >= 12, 'charts for the main sensors: ' + charts.length);
  assert.equal((html.match(/aria-label="[^"]*\(simulated\)"/g) || []).length, charts.length, 'every chart is labelled simulated');
  for (const s of ['31 °C at 33 m', '+9 °C at 33 m', 'peak 0.55', 'now 0.42', '0.6 L/s, 01:00–04:00', 'design ref. 450 (to verify)', '>1.2<', '>2.1<', 'dry all day']) assert.ok(html.includes(s), 'chart label ' + s);
  assert.equal((html.match(/SIMULATED · not installed/g) || []).length, CFG.sensors.length, 'every callout says simulated / not installed');
  assert.ok(html.includes(read('place.js').trim().slice(0, 200)), 'place.js is inlined');
});

/* place.js: the pure callout placement used on the test-install slides */
const TP = require(path.join(deck, 'place.js'));
const ov = (a, b) => TP.area(a, b) > 0;
const dot = (x, y, r) => [x - r, y - r, x + r, y + r];
test('callout placement: beside the marker, inside the image, clear of other markers', () => {
  const B = [0, 0, 780, 630], sizes = [{w: 420, h: 330}, {w: 350, h: 280}, {w: 290, h: 240}];
  const c = TP.place({anchor: {x: 200, y: 300}, sizes, bounds: B, hard: [dot(200, 300, 34)], gap: 46});
  assert.equal(c.stage, 1); assert.equal(c.tier, 0); assert.equal(c.x, 246, 'first choice: right of the marker'); assert.equal(c.hard, 0);
  // near the right edge it flips to the left
  const r = TP.place({anchor: {x: 700, y: 300}, sizes, bounds: B, hard: [dot(700, 300, 34)], gap: 46});
  assert.ok(r.x + r.w <= 700 - 46 + .01 && r.x >= 0, 'left of the marker');
  // another marker on the right and below: the card goes elsewhere, never on it
  const others = [dot(330, 300, 26), dot(200, 420, 26)];
  const o = TP.place({anchor: {x: 200, y: 300}, sizes, bounds: B, hard: [dot(200, 300, 34), ...others], gap: 46});
  const rect = [o.x, o.y, o.x + o.w, o.y + o.h];
  assert.equal(o.hard, 0); for (const m of others) assert.ok(!ov(rect, m)); assert.ok(rect[0] >= 0 && rect[1] >= 0 && rect[2] <= 780 && rect[3] <= 630);
  // a crowded image: smaller card or a nearby grid spot, still no hard overlap
  const crowd = [dot(260, 300, 26), dot(140, 300, 26), dot(200, 240, 26), dot(200, 360, 26)];
  const q = TP.place({anchor: {x: 200, y: 300}, sizes, bounds: B, hard: [dot(200, 300, 34), ...crowd], gap: 46});
  assert.equal(q.hard, 0); assert.ok(q.stage >= 1);
  // impossible: least overlap, reported as stage 3
  const z = TP.place({anchor: {x: 50, y: 50}, sizes: [{w: 100, h: 100}], bounds: [0, 0, 120, 120], hard: [[0, 0, 120, 120]]});
  assert.equal(z.stage, 3); assert.ok(z.hard > 0);
});
test('callout placement: a diagonal pipe blocks only its own path, soft shapes only when there is a choice, prefer keeps the spot', () => {
  const pipe = TP.shapeRects([['seg', 0, 0, 600, 600, 6]]);
  assert.ok(pipe.length >= 30, 'cut into pieces');
  assert.ok(!pipe.some(r => ov(r, [400, 50, 600, 200])), 'the empty corner above a diagonal is free');
  assert.equal(TP.shapeRects([['ring', 100, 100, 50, 5]]).length, 24);
  assert.deepEqual(TP.shapeRects([['dot', 10, 10, 4]], 2), [[12, 12, 28, 28]]);
  const sizes = [{w: 200, h: 120}], B = [0, 0, 600, 600];
  const c = TP.place({anchor: {x: 300, y: 300}, sizes, bounds: B, hard: [dot(300, 300, 30), ...pipe], gap: 40});
  assert.equal(c.hard, 0); assert.ok(!pipe.some(r => ov(r, [c.x, c.y, c.x + c.w, c.y + c.h])), 'card off the selected pipe');
  const s = TP.place({anchor: {x: 300, y: 300}, sizes, bounds: B, hard: [dot(300, 300, 30)], soft: [[330, 200, 600, 420]], gap: 40});
  assert.equal(s.soft, 0, 'soft area avoided when a clean spot exists');
  const p = TP.place({anchor: {x: 300, y: 300}, sizes, bounds: B, hard: [dot(300, 300, 30)], gap: 40, prefer: {tier: 0, dx: -240, dy: -60}});
  assert.equal(p.stage, 0); assert.equal(p.x, 60);
  const ln = TP.leader({x: 340, y: 240, w: 200, h: 120}, 300, 300, 30);
  assert.deepEqual(ln.slice(2), [340, 300]); assert.ok(Math.abs(ln[0] - 330) < 1e-9);
  assert.equal(TP.leader({x: 280, y: 280, w: 50, h: 50}, 300, 300, 30), null, 'no leader when the card touches the marker');
});

test('live views: the viewer loads a scene\'s anchor layers first (deck speed-up)', () => {
  const bim = fs.readFileSync(path.join(root, 'scan-bim.html'), 'utf8');
  assert.match(bim, /async function ovLayerOrder\(\)/);
  assert.match(bim, /for\(const key of await ovLayerOrder\(\)\)/);
});

test('slide order (Oct 29 talk): 15 main slides in two tagged parts without section dividers, then one appendix divider and the backup slides', () => {
  const ids = [...html.matchAll(/<section class="slide" id="([^"]+)">/g)].map(m => m[1]);
  assert.deepEqual(ids, ['cover', 'week-energy', 'week-facilities', 'week-quest', 'bms', 'open-ceiling', 'test-installs',
    'twin-concept', 'twin-hvac', 'twin-water', 'twin-power', 'twin-fan', 'pilot', 'week-asks', 'thanks',
    'part-A', 'ready', 'sensing', 'fiber', 'ce278', 'mems', 'wsn']);
  const notes = JSON.parse(html.match(/const NOTES=(\[.*?\]);\n/s)[1]);
  assert.equal(notes.length, ids.length, 'one notes entry per slide');
  assert.ok(!/SECTION 0\d|Part (one|two|three)/i.test(html), 'no leftover section numbers or "part N" notes');
  /* the follow-up email has not been sent: it goes out after the meeting; no "team / combined follow-up" wording */
  assert.ok(html.includes('Follow-up email with the final request list goes out after today’s meeting'));
  assert.ok(!/combined follow-up|each member|existing email threads/i.test(html));
  /* parts are header tags, not slides: Dashboard = the energy slide, Grimes = facilities … pilot */
  const sec = Object.fromEntries([...html.matchAll(/<section class="slide" id="([^"]+)">([\s\S]*?)<\/section>/g)].map(m => [m[1], m[2]]));
  const tag = id => (sec[id].match(/>(DASHBOARD|GRIMES) · /) || [])[1] || null;
  assert.equal(tag('week-energy'), 'DASHBOARD');
  for (const id of ids.slice(2, 13)) assert.equal(tag(id), 'GRIMES', 'Grimes tag on ' + id);
  for (const id of ['cover', 'thanks', ...ids.slice(15)]) assert.equal(tag(id), null, 'no part tag on ' + id);
  assert.equal((sec['week-asks'].match(/>(DASHBOARD|GRIMES)</g) || []).length, 4, 'each ask tagged by part');
  /* SkySpark is suggested by Facilities, not decided */
  assert.ok(!/moving to SkySpark|recommends SkySpark|BMO → SkySpark|SkySpark requested|switches its meter source/i.test(html));
  assert.match(sec['week-energy'], /Suggested by Facilities; nothing decided yet/);
  assert.match(sec['week-quest'], /Not tested yet · waiting for the device/);
  assert.ok(!/3\u00a0cm|Check in cm/.test(sec['week-quest'].replace(/&nbsp;/g, '\u00a0')), 'accuracy targets are in the notes only');
});
