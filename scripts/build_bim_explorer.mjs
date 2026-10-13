#!/usr/bin/env node
/** Reproducible static page build. No source geometry is rewritten. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const root=fileURLToPath(new URL('../',import.meta.url));
const source='viewer-src/bim-explorer';
const target='grimes-bim-explorer.html';
const assets='bim-explorer-assets';
const version='0.25.0';
const args=['--yes','--prefer-offline','--package=esbuild@'+version,'esbuild',source+'/viewer.mjs',
  '--bundle','--format=esm','--platform=browser','--target=es2022',
  '--external:three','--external:three/*','--legal-comments=inline','--charset=utf8','--log-level=warning'];
const bundled=spawnSync(process.platform==='win32'?'npx.cmd':'npx',args,{
  cwd:root,encoding:'utf8',maxBuffer:10*1024*1024,shell:false
});
if(bundled.error)throw bundled.error;
if(bundled.status!==0)throw new Error(bundled.stderr||'Pinned esbuild invocation failed.');
const template=fs.readFileSync(path.join(root,source,'index.template.html'),'utf8');
const css=fs.readFileSync(path.join(root,source,'style.css'),'utf8');
for(const marker of ['<!-- BIM_EXPLORER_STYLES -->','<!-- BIM_EXPLORER_APP -->']){
  if(template.split(marker).length!==2)throw new Error('Template needs exactly one '+marker);
}
const js=bundled.stdout.replace(/<\/script/gi,'<\\/script');
const html=template.replace('<!-- BIM_EXPLORER_STYLES -->',()=>'<style>\n'+css+'\n</style>')
  .replace('<!-- BIM_EXPLORER_APP -->',()=>'<script type="module">\n'+js+'\n</script>');
const manifestPath=path.join(root,assets,'build-manifest.json');
const walk=directory=>fs.readdirSync(path.join(root,directory),{withFileTypes:true})
  .flatMap(entry=>entry.isDirectory()?walk(directory+'/'+entry.name):[directory+'/'+entry.name]);
const files=[target,'scripts/build_bim_explorer.mjs',...walk(source),...walk(assets)]
  .filter(name=>name!==assets+'/build-manifest.json').sort();
const record=name=>{
  const buffer=name===target?Buffer.from(html):fs.readFileSync(path.join(root,name));
  return {path:name,bytes:buffer.length,sha256:createHash('sha256').update(buffer).digest('hex')};
};
const manifest=JSON.stringify({schema:'grimes-bim-explorer-build/1',engineVersion:'0.169.0',bundlerVersion:version,
  output:target,sourceGeometryModified:false,files:files.map(record)},null,2)+'\n';
if(process.argv.includes('--check')){
  if(!fs.existsSync(path.join(root,target))||fs.readFileSync(path.join(root,target),'utf8')!==html||
     !fs.existsSync(manifestPath)||fs.readFileSync(manifestPath,'utf8')!==manifest){
    throw new Error('Generated public page or manifest is stale. Run node scripts/build_bim_explorer.mjs.');
  }
  console.log('Public BIM page and build manifest are reproducible and current.');
}else{
  fs.writeFileSync(path.join(root,target),html);
  fs.writeFileSync(manifestPath,manifest);
  console.log(JSON.stringify({output:target,bytes:Buffer.byteLength(html),files:files.length,
    sha256:createHash('sha256').update(html).digest('hex')}));
}
