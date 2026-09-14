const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto'),{spawnSync}=require('node:child_process');
(async()=>{
 if(!process.env.GAUSSIAN_MODULE)throw Error('Set GAUSSIAN_MODULE to the pinned 0.4.7 ESM build');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'grimes-codec-'));
 try{
  const properties=['x','y','z','opacity','scale_0','scale_1','scale_2','rot_0','rot_1','rot_2','rot_3','f_dc_0','f_dc_1','f_dc_2'];
  const header=Buffer.from('ply\nformat binary_little_endian 1.0\ncomment Synthetic codec test; not a trained reconstruction\nelement vertex 3\n'+properties.map(p=>'property float '+p+'\n').join('')+'end_header\n');
  const data=Buffer.alloc(3*properties.length*4);
  for(let i=0;i<3;i++)[i-1,2,-3,3,-3,-3,-3,1,0,0,0,.5,.2,.1].forEach((v,j)=>data.writeFloatLE(v,(i*properties.length+j)*4));
  const source=path.join(dir,'fixture.ply'),output=path.join(dir,'fixture.ksplat');fs.writeFileSync(source,Buffer.concat([header,data]));
  const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex'),before=hash(source);
  const run=()=>spawnSync(process.execPath,[path.join(__dirname,'../scripts/encode_gaussian.mjs'),source,output],{env:process.env,encoding:'utf8'});
  const result=run();assert.equal(result.status,0,result.stderr);assert.equal(hash(source),before,'source unchanged');
  const report=JSON.parse(fs.readFileSync(output+'.json'));assert.equal(report.splatCount,3);assert.equal(report.sphericalHarmonicsDegree,0);assert.equal(report.outputSha256,hash(output));
  const {SplatBuffer}=await import(process.env.GAUSSIAN_MODULE),bytes=fs.readFileSync(output),packed=new SplatBuffer(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
  assert.equal(packed.getSplatCount(),3);const centers=[];
  for(let i=0;i<3;i++){const point={};packed.getSplatCenter(i,point);centers.push(point);}
  centers.sort((a,b)=>a.x-b.x);centers.forEach((p,i)=>assert.ok(Math.hypot(p.x-(i-1),p.y-2,p.z+3)<.001,'metric frame preserved within codec quantization'));
  assert.notEqual(run().status,0,'existing outputs cannot be overwritten');
  const rgb=path.join(dir,'plain-points.ply');fs.writeFileSync(rgb,'ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty float x\nend_header\n');
  const invalid=spawnSync(process.execPath,[path.join(__dirname,'../scripts/encode_gaussian.mjs'),rgb,path.join(dir,'invalid.ksplat')],{env:process.env,encoding:'utf8'});assert.notEqual(invalid.status,0);assert.equal(fs.existsSync(path.join(dir,'invalid.ksplat')),false);
  console.log('PASS: real codec round-trip, count/metric centers/SH0, source/hash preservation, overwrite and non-Gaussian input rejection');
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exit(1)});
