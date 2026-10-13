import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const root=fileURLToPath(new URL('../',import.meta.url));
const deploymentURL=new URL('../viewer-src/bim-explorer/deployment.mjs',import.meta.url);
async function paths(url){
  assert.ok(fs.existsSync(deploymentURL),'The public deployment URL adapter must exist.');
  return (await import(deploymentURL.href)).deploymentPaths(url);
}

test('GitHub Pages resolves source geometry within the project subpath',async()=>{
  const p=await paths('https://doe2park.github.io/Graduate-Project/grimes-bim-explorer.html?model=full');
  assert.equal(p.source('buildings/grimes/grimes-conduit.glb'),'https://doe2park.github.io/Graduate-Project/buildings/grimes/grimes-conduit.glb');
  assert.equal(p.asset('source-catalog.json'),'https://doe2park.github.io/Graduate-Project/bim-explorer-assets/source-catalog.json');
  assert.equal(p.asset('draco/'),'https://doe2park.github.io/Graduate-Project/bim-explorer-assets/draco/');
});
test('domain-root and local preview paths are also supported',async()=>{
  assert.equal((await paths('http://localhost:8934/grimes-bim-explorer.html')).asset('sample.glb'),'http://localhost:8934/bim-explorer-assets/sample.glb');
  assert.equal((await paths('http://localhost:8934/Graduate-Project/grimes-bim-explorer.html')).asset('regional/manifest.json'),'http://localhost:8934/Graduate-Project/bim-explorer-assets/regional/manifest.json');
});
test('asset and source paths cannot escape their configured project directory',async()=>{
  const p=await paths('https://example.test/Graduate-Project/grimes-bim-explorer.html');
  for(const value of ['/source/x','../outside','https://elsewhere.test/x','//elsewhere.test/x','%2e%2e/outside']){
    assert.throws(()=>p.asset(value),/relative|outside/i,value);
    assert.throws(()=>p.source(value),/relative|outside/i,value);
  }
});
test('generated page is self-contained application code with pinned engine imports',()=>{
  const file=path.join(root,'grimes-bim-explorer.html');
  assert.ok(fs.existsSync(file),'Build the public page before testing its output.');
  const html=fs.readFileSync(file,'utf8');
  assert.match(html,/<style>[\s\S]*\.workspace/);
  assert.match(html,/<script type="module">[\s\S]*loadExample/);
  assert.match(html,/https:\/\/cdn\.jsdelivr\.net\/npm\/three@0\.169\.0\/build\/three\.module\.js/);
  assert.doesNotMatch(html,/<script[^>]+src=/);
  assert.doesNotMatch(html,/<link[^>]+rel="stylesheet"/);
  assert.doesNotMatch(html,/BIM_EXPLORER_(?:APP|STYLES)/);
  assert.doesNotMatch(html,/(?:href|src)=["']\/(?:web|ar|quest|three)(?:[\/\."'])/);
  assert.doesNotMatch(html,/localhost|127\.0\.0\.1|\/source\//);
});
test('public navigation and teaching downloads stay inside the project',()=>{
  const html=fs.readFileSync(path.join(root,'grimes-bim-explorer.html'),'utf8');
  for(const href of ['grimes-bim-explorer.html','scan-compare.html','campus-energy-dashboard.html','LICENSE.md','bim-explorer-assets/sample.glb','bim-explorer-assets/sample.json'])assert.ok(html.includes(`href="${href}"`),href);
  assert.match(html,/Web workspace/);
  assert.doesNotMatch(html,/Connect headset|href="\/ar\/"|Local workspace/);
});
test('all regional geometry files retain audited byte lengths and counts',()=>{
  const assets=path.join(root,'bim-explorer-assets/regional');
  const m=JSON.parse(fs.readFileSync(path.join(assets,'manifest.json')));
  assert.equal(m.objectCount,492);assert.equal(m.triangleInstances,80755);assert.equal(m.layers.length,8);
  for(const l of m.layers)assert.equal(fs.statSync(path.join(assets,l.file)).size,l.bytes,l.file);
  assert.ok(fs.statSync(path.join(assets,m.elements)).size>0);
});
test('existing full-building catalog preserves identities and triangle counts',()=>{
  const c=JSON.parse(fs.readFileSync(path.join(root,'bim-explorer-assets/source-catalog.json')));
  assert.equal(c.objects,66620);assert.equal(c.triangles,48728223);assert.equal(c.segments,385803);
  assert.equal(c.layers.length,10);
  for(const layer of c.layers){assert.match(layer.metadataSHA256,/^[a-f0-9]{64}$/);for(const part of layer.parts){assert.match(part.sha256,/^[a-f0-9]{64}$/);assert.ok(part.path.startsWith('buildings/grimes/'));}}
});
test('Draco decoder files and third-party notices are present',()=>{
  for(const name of ['draco_decoder.js','draco_decoder.wasm','draco_wasm_wrapper.js','LICENSE.txt','README.md'])assert.ok(fs.statSync(path.join(root,'bim-explorer-assets/draco',name)).size>0,name);
  assert.ok(fs.statSync(path.join(root,'bim-explorer-assets/THREE-LICENSE.txt')).size>0);
});
test('build output records hashes of exactly the shipped app and asset inputs',()=>{
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'bim-explorer-assets/build-manifest.json')));
  assert.equal(manifest.engineVersion,'0.169.0');assert.equal(manifest.bundlerVersion,'0.25.0');
  for(const row of manifest.files){const b=fs.readFileSync(path.join(root,row.path));assert.equal(createHash('sha256').update(b).digest('hex'),row.sha256,row.path);assert.equal(b.length,row.bytes);}
});
