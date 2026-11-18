import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as model from '../viewer-src/bim-explorer/source-model.mjs';

test('full source scope does not claim a complete installed building', () => {
  assert.equal(model.FULL_SOURCE_SCOPE, 'All available source BIM · 10 disciplines · Source coverage is incomplete');
});
test('source coverage wording does not replace modelling work with a missing-duct notice', () => {
  const source = fs.readFileSync(new URL('../viewer-src/bim-explorer/viewer.mjs', import.meta.url), 'utf8');
  const template = fs.readFileSync(new URL('../viewer-src/bim-explorer/index.template.html', import.meta.url), 'utf8');
  assert.ok(!source.includes('coverageNote(mode,floor)'));
  assert.ok(!template.includes('id="coverage-note"'));
  assert.doesNotMatch(template, /Complete BIM/);
});
