/* twin/ask-twin.js (laptop panel): access-code helpers. The panel itself needs the viewer; required here without one it only
   exports its pure helpers.   node --test tests/ask-twin.test.cjs */
const {test} = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
globalThis.window = {};   // no twinViewerApi, no document: the file returns right after exporting
const H = require('../twin/ask-twin.js');
const src = fs.readFileSync(path.join(__dirname, '..', 'twin', 'ask-twin.js'), 'utf8');

test('code= is read from the page URL (case, dashes and junk dropped)', () => {
  assert.equal(H.accessCode('?ask=1&code=ab23cd'), 'AB23CD');
  assert.equal(H.accessCode('?code=ab-23 cd'), 'AB23CD');
  assert.equal(H.accessCode('?code=<b>x</b>'), 'BXB');
  assert.equal(H.accessCode('?ask=1'), '');
  assert.equal(H.accessCode(''), '');
  assert.equal(H.accessCode('?code=' + 'A'.repeat(80)).length, 32);
});

test('the code goes out as X-Ask-Code only when there is one', () => {
  assert.deepEqual(H.headers('AB23CD', {'Content-Type': 'application/json'}), {'Content-Type': 'application/json', 'X-Ask-Code': 'AB23CD'});
  assert.deepEqual(H.headers('', {'Content-Type': 'audio/webm'}), {'Content-Type': 'audio/webm'});
});

test('401 / 429 become clear sentences; other statuses are left alone', () => {
  assert.match(H.refusalText(401, {reason: 'code_required'}), /Access code needed/);
  assert.match(H.refusalText(401, {reason: 'code_wrong'}), /Wrong access code/);
  assert.match(H.refusalText(401, null), /Access code needed/);
  assert.equal(H.refusalText(429, {error: 'Daily budget reached for the AI answers. It resets at midnight.', reason: 'budget'}),
    'Daily budget reached for the AI answers. It resets at midnight.');
  assert.match(H.refusalText(429, {retry_after_s: 12}), /12 s/);
  assert.equal(H.refusalText(500, {}), null);
});

test('ask and transcribe send the code; the panel offers a code box on 401', () => {
  assert.match(src, /fetch\('\/api\/ask', \{method: 'POST', headers: H\.headers\(state\.code/);
  assert.match(src, /fetch\('\/api\/transcribe', \{method: 'POST', headers: H\.headers\(state\.code/);
  assert.match(src, /code: H\.accessCode\(location\.search\)/);
  assert.match(src, /showCodeBox/);
  assert.doesNotMatch(src, /localStorage|sessionStorage/);   // the code lives in the URL / memory only
});

// Live answers (Nov 2026): one plain paragraph for non-experts, then "Evidence: [[id]] ..." (ids only as chips).
const PLAIN = 'This is a supply air vent (diffuser) in the ceiling of Level 1, probably in room 120. It blows in air that a VAV box upstream controls.\nEvidence: [[388279]] [[400766]]';
const CARD = '**Answer:** [[388279]] is an air outlet on L1 · confidence: low\n**Why:**\n- design record';

test('plain answers split into the visible paragraph and the evidence ids', () => {
  assert.equal(H.isCard(PLAIN), false);
  assert.equal(H.isCard(CARD), true);
  assert.equal(H.isCard('**Answer:** slip\nEvidence: [[1]]'), false);   // an Evidence line means the plain format
  const {body, evidence} = H.splitAnswer(PLAIN);
  assert.equal(body, PLAIN.split('\n')[0]);
  assert.deepEqual(evidence, ['388279', '400766']);
  assert.deepEqual(H.splitAnswer('Comes from [[400766]].\nEvidence: [[388279]] [[400766]]').evidence, ['388279', '400766']);
  assert.deepEqual(H.splitAnswer('Evidence: [[38').evidence, []);   // half-streamed line: no chip yet
});

test('the primary (highlighted, marker) element is the first Evidence id, or the card lead id', () => {
  assert.equal(H.primaryId(PLAIN), '388279');
  assert.equal(H.primaryId('The air comes from a VAV box.\nEvidence: [[400766]] [[388279]]'), '400766');
  assert.equal(H.primaryId(CARD), '388279');
  assert.equal(H.primaryId('No evidence here.'), null);
});

test('spoken fallback says the card paragraph with units spelled out, never the ids', () => {
  assert.equal(H.speakPlain('The VAV box is ~3 m away, 2.4 °C warm.'), 'The VAV box is about 3 metres away, 2.4 degrees warm.');
  assert.equal(H.speakPlain('Fed by [[400766]].', id => 'VAV box'), 'Fed by the VAV box.');
});

test('the panel renders plain answers as a paragraph plus an Evidence chip row', () => {
  assert.match(src, /if \(!H\.isCard\(text\)\) \{/);
  assert.match(src, /class="at-ev"><span class="at-ev-k">Evidence<\/span>/);
  assert.match(src, /const primary = H\.primaryId\(answer\)/);
  assert.match(src, /c\?\.label \|\| c\?\.type/);   // chips use the plain label (diffuser, VAV box), not the CAD code
});
