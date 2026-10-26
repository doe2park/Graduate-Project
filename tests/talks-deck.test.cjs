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
  assert.ok(html.includes('data-nopreload="1"'), 'live views lazy-load only on their slide');
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
      for (const bad of [/2026-10-18/, /Oct(ober)? 18/, /capture-local/, ...(rel === 'README.md' ? [] : [/127\.0\.0\.1|localhost/]), /@gmail\.com|@berkeley\.edu/, /ghp_[A-Za-z0-9]{10}|github_pat_/, /Chung/])
        assert.ok(!bad.test(rel === 'img/SOURCES.md' ? t.replace('There is no imagery from the Oct 18 capture', '') : t), rel + ' matches ' + bad);
    }
  }
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
