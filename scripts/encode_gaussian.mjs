/** Optional browser derivative of an optimized PLY; never rewrites its source.
 * Requires GaussianSplats3D 0.4.7 (GAUSSIAN_MODULE may point to its ESM build).
 * KSplat compression 2 retains SH2 with quantized parameters; it is lossy.
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const [source,target]=process.argv.slice(2);
if(!source||!target||path.resolve(source)===path.resolve(target))throw Error('Usage: node scripts/encode_gaussian.mjs input.ply new-output.ksplat');
if(fs.existsSync(target)||fs.existsSync(target+'.json'))throw Error('Use new output paths');
if(!target.toLowerCase().endsWith('.ksplat'))throw Error('Output must end with .ksplat');
if(fs.statSync(source).size>1024**3)throw Error('Input exceeds the local conversion budget');
const bytes=fs.readFileSync(source),header=bytes.subarray(0,4096).toString('ascii').split('end_header\n')[0];
if(!header.startsWith('ply\nformat binary_little_endian 1.0\n'))throw Error('Expected binary little-endian optimized PLY');
for(const field of ['opacity','scale_0','scale_1','scale_2','rot_0','rot_1','rot_2','rot_3','f_dc_0','f_dc_1','f_dc_2'])if(!header.includes('property float '+field+'\n'))throw Error('Expected optimized Gaussian parameters');
const sourceCount=Number(header.match(/element vertex (\d+)/)?.[1]);
if(!Number.isSafeInteger(sourceCount)||sourceCount<1||sourceCount>3000000)throw Error('Invalid count or exceeded local viewer budget');
const moduleURL=import.meta.resolve(process.env.GAUSSIAN_MODULE||'@mkkellogg/gaussian-splats-3d');
let directory=path.dirname(fileURLToPath(moduleURL)),version=null;
while(true){
 const packageFile=path.join(directory,'package.json');
 if(fs.existsSync(packageFile)){const info=JSON.parse(fs.readFileSync(packageFile));if(info.name==='@mkkellogg/gaussian-splats-3d'){version=info.version;break;}}
 const parent=path.dirname(directory);if(parent===directory)break;directory=parent;
}
if(version!=='0.4.7')throw Error('Use the tested GaussianSplats3D 0.4.7 package');
const {PlyParser,SplatBufferGenerator}=await import(moduleURL);
const array=PlyParser.parseToUncompressedSplatArray(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),2);
const packed=SplatBufferGenerator.getStandardGenerator(1,2).generateFromUncompressedSplatArray(array);
const output=Buffer.from(packed.bufferData),count=packed.getSplatCount();
if(!count||count>sourceCount)throw Error('Invalid encoded Gaussian count');
fs.mkdirSync(path.dirname(path.resolve(target)),{recursive:true});fs.writeFileSync(target,output,{flag:'wx'});
const sha=data=>crypto.createHash('sha256').update(data).digest('hex');
const report={software:'GaussianSplats3D 0.4.7',format:'KSplat compression level 2',sourceCount,sphericalHarmonicsDegree:array.sphericalHarmonicsDegree,splatCount:count,sourceBytes:bytes.length,outputBytes:output.length,sourceSha256:sha(bytes),outputSha256:sha(output),method:'Lossy browser derivative: quantized centers, scales, rotations, color and retained spherical harmonics; alpha threshold 1. Source PLY is unchanged. No scene-coordinate transform.'};
fs.writeFileSync(target+'.json',JSON.stringify(report,null,2),{flag:'wx'});console.log(JSON.stringify(report,null,2));
