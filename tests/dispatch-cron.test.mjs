import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

const BASE = 'https://api.github.com/repos/doe2park/Graduate-Project/actions/workflows';
const CAMPUS = `${BASE}/bmo-campus-energy.yml/dispatches`;
const GRIMES = `${BASE}/bmo-fetch.yml/dispatches`;

const realFetch = globalThis.fetch;
const realError = console.error;
let calls, errors, responder;

beforeEach(() => {
  calls = [];
  errors = [];
  responder = () => new Response(null, { status: 204 });
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return responder(url, init); };
  console.error = (...a) => errors.push(a.join(' '));
});
afterEach(() => { globalThis.fetch = realFetch; console.error = realError; });

const load = async () => (await import('../worker/dispatch-cron/worker.js')).default;
const ctx = { waitUntil() {} };

test('*/15 cron dispatches campus workflow', async () => {
  const w = await load();
  await w.scheduled({ cron: '*/15 * * * *' }, { GITHUB_TOKEN: 'tok' }, ctx);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, CAMPUS);
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.headers.Authorization, 'Bearer tok');
  assert.equal(calls[0].init.headers.Accept, 'application/vnd.github+json');
  assert.equal(calls[0].init.headers['X-GitHub-Api-Version'], '2022-11-28');
  assert.ok(calls[0].init.headers['User-Agent']);
  assert.deepEqual(JSON.parse(calls[0].init.body), { ref: 'main' });
});

test('offset cron dispatches Grimes workflow', async () => {
  const w = await load();
  await w.scheduled({ cron: '7,22,37,52 * * * *' }, { GITHUB_TOKEN: 'tok' }, ctx);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, GRIMES);
});

test('unknown cron does nothing and logs', async () => {
  const w = await load();
  await w.scheduled({ cron: '0 0 * * *' }, { GITHUB_TOKEN: 'tok' }, ctx);
  assert.equal(calls.length, 0);
  assert.equal(errors.length, 1);
});

test('missing token logs error and does not fetch', async () => {
  const w = await load();
  await w.scheduled({ cron: '*/15 * * * *' }, {}, ctx);
  assert.equal(calls.length, 0);
  assert.match(errors.join('\n'), /GITHUB_TOKEN/);
});

test('non-204 logs status and body, retries once', async () => {
  const w = await load();
  responder = () => new Response('Bad credentials', { status: 401 });
  await w.scheduled({ cron: '*/15 * * * *' }, { GITHUB_TOKEN: 'tok' }, ctx);
  assert.equal(calls.length, 2);
  assert.match(errors.join('\n'), /401/);
  assert.match(errors.join('\n'), /Bad credentials/);
});

test('fetch handler returns 404', async () => {
  const w = await load();
  for (const path of ['/', '/health', '/dispatch']) {
    const res = await w.fetch(new Request('https://x.example' + path, { method: 'POST' }), {}, ctx);
    assert.equal(res.status, 404);
  }
  assert.equal(calls.length, 0);
});
