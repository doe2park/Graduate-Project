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
