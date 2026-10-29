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

test('test-install slides: sensor details sit beside the image (never on it), with simulated charts from the registry / feed', () => {
  const panels = [...html.matchAll(/<div class="twpanel" style="left:([\d.]+)px;top:([\d.]+)px;width:([\d.]+)px;height:([\d.]+)px">/g)].map(m => m.slice(1).map(Number));
  const figs = [...html.matchAll(/<div class="tw" data-slug="[^"]+"[^>]*style="left:([\d.]+)px;top:([\d.]+)px;width:([\d.]+)px;height:([\d.]+)px">/g)].map(m => m.slice(1).map(Number));
  assert.equal(panels.length, 5); assert.equal(figs.length, 5);
  panels.forEach(([pl, pt, pw, ph], i) => { const [fl, , fw] = figs[i]; assert.ok(pl >= fl + fw, 'panel right of the image on concept slide ' + (i + 1)); assert.ok(pt + ph <= 1080 * 5.0 / 5.625, 'panel above the footnote'); });
  assert.ok(!/class="twcard/.test(html), 'no floating popup on the screenshot');
  const charts = html.match(/<svg class="twc"/g) || [];
  assert.ok(charts.length >= 12, 'charts for the main sensors: ' + charts.length);
  assert.equal((html.match(/aria-label="[^"]*\(simulated\)"/g) || []).length, charts.length, 'every chart is labelled simulated');
  for (const s of ['31 °C at 33 m', '+9 °C at 33 m', 'peak 0.55', 'now 0.42', '0.6 L/s, 01:00–04:00', 'design ref. 450 (to verify)', '>1.2<', '>2.1<', 'dry all day']) assert.ok(html.includes(s), 'chart label ' + s);
  assert.equal((html.match(/SIMULATED · not installed/g) || []).length, CFG.sensors.length, 'every info panel says simulated / not installed');
});

test('live views: the viewer loads a scene\'s anchor layers first (deck speed-up)', () => {
  const bim = fs.readFileSync(path.join(root, 'scan-bim.html'), 'utf8');
  assert.match(bim, /async function ovLayerOrder\(\)/);
  assert.match(bim, /for\(const key of await ovLayerOrder\(\)\)/);
});
