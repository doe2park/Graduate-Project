/* registration-core.js — pure Scan->BIM registration maths for registration-workbench.html and scan-compare.html.
   Mirrored by scripts/registration_fit.py (tests/registration-core.test.cjs checks both give the same numbers).

   Model: rigid yaw about +Y plus XYZ translation, scale fixed at 1 (same as the accepted May ICP):
     p_bim = R_y(theta) p_scan + t,  R_y = [[c,0,s],[0,1,0],[-s,0,c]]   (Three.js rotation.y convention)
   Both frames are Y-up metres. Residuals are internal consistency, never surveyed accuracy unless every
   check point is marked surveyed. No DOM, no network. Works as a browser global (RegistrationCore) or CommonJS. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.RegistrationCore=api;})(typeof self!=='undefined'?self:this,function(){
'use strict';
const SCHEMA='grimes-registration-candidate/1',PAIRS_SCHEMA='grimes-registration-pairs/1',MIN_FIT_PAIRS=4,MIN_SPREAD_METRES=.5;
const CANDIDATE_STATUSES=['landmark-fit-unsurveyed','landmark-fit-surveyed-checks','icp-refined-unsurveyed'];
const D2R=Math.PI/180,R2D=180/Math.PI;
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2]);
function vec(v,n=3){if(!Array.isArray(v)||v.length!==n||!v.every(x=>typeof x==='number'&&Number.isFinite(x)))throw new Error('Coordinates must be finite '+n+'-vectors');return v;}
function apply(reg,p){const a=reg.rotationYDegrees*D2R,c=Math.cos(a),s=Math.sin(a),t=reg.translation;return [c*p[0]+s*p[2]+t[0],p[1]+t[1],-s*p[0]+c*p[2]+t[2]];}
function invert(reg,p){const a=reg.rotationYDegrees*D2R,c=Math.cos(a),s=Math.sin(a),t=reg.translation,x=p[0]-t[0],y=p[1]-t[1],z=p[2]-t[2];return [c*x-s*z,y,s*x+c*z];}
/* rotate a direction about +Y by deg (Three.js rotation.y sense); used for per-station photo heading offsets */
function rotateY(v,deg){const a=deg*D2R,c=Math.cos(a),s=Math.sin(a);return [c*v[0]+s*v[2],v[1],-s*v[0]+c*v[2]];}

function fitYawTranslation(pairs){
 if(pairs.length<2)throw new Error('Need at least 2 pairs for a yaw + XYZ fit');
 const n=pairs.length,a=[0,0,0],b=[0,0,0];
 for(const p of pairs){vec(p.scan);vec(p.bim);}
 /* sum then divide, exactly as the Python mirror, for bit-level agreement */
 for(let k=0;k<3;k++){a[k]=pairs.reduce((s,p)=>s+p.scan[k],0)/n;b[k]=pairs.reduce((s,p)=>s+p.bim[k],0)/n;}
 let c=0,s=0,spread=0;
 for(const p of pairs){const x=p.scan[0]-a[0],z=p.scan[2]-a[2],X=p.bim[0]-b[0],Z=p.bim[2]-b[2];c+=x*X+z*Z;s+=z*X-x*Z;spread+=x*x+z*z;}
 if(Math.sqrt(spread/n)<MIN_SPREAD_METRES||Math.hypot(c,s)<1e-9)throw new Error('Landmarks are too close together horizontally to determine yaw (spread < '+MIN_SPREAD_METRES.toFixed(1)+' m)');
 const reg={rotationYDegrees:Math.atan2(s,c)*R2D,translation:[0,0,0]},ra=apply(reg,a);
 reg.translation=[b[0]-ra[0],b[1]-ra[1],b[2]-ra[2]];
 reg.residualsMetres=pairs.map(p=>dist(apply(reg,p.scan),p.bim));
 return reg;
}
function stats(errors){if(!errors.length)return{rmsMetres:null,maxMetres:null,medianMetres:null};const e=[...errors].sort((x,y)=>x-y),m=e.length;return{rmsMetres:Math.sqrt(e.reduce((s,v)=>s+v*v,0)/m),maxMetres:e[m-1],medianMetres:m%2?e[(m-1)/2]:.5*(e[m/2-1]+e[m/2])};}
function residualRows(reg,pairs,inliers){return pairs.map((p,i)=>{const q=apply(reg,p.scan),d=[q[0]-p.bim[0],q[1]-p.bim[1],q[2]-p.bim[2]];const row={id:p.id??String(i),errorMetres:Math.sqrt(d[0]*d[0]+d[1]*d[1]+d[2]*d[2]),horizontalMetres:Math.hypot(d[0],d[2]),verticalMetres:d[1]};if(inliers)row.inlier=inliers.has(i);return row;});}
function leaveOneOut(pairs){
 if(pairs.length<3)throw new Error('Leave-one-out needs at least 3 fit pairs');
 const errors=pairs.map((p,i)=>{const reg=fitYawTranslation(pairs.filter((_,j)=>j!==i));return{id:p.id??String(i),errorMetres:dist(apply(reg,p.scan),p.bim)};});
 return{errors,...stats(errors.map(e=>e.errorMetres))};
}
/* Deterministic exhaustive RANSAC over all 2-pair minimal samples (identical order and tie-break in Python) */
function ransac(pairs,threshold=.25){
 let best=null;
 for(let i=0;i<pairs.length;i++)for(let j=i+1;j<pairs.length;j++){
  const pi=pairs[i].scan,pj=pairs[j].scan;if(Math.hypot(pi[0]-pj[0],pi[2]-pj[2])<2*MIN_SPREAD_METRES)continue;
  let reg;try{reg=fitYawTranslation([pairs[i],pairs[j]]);}catch{continue;}
  const errs=pairs.map(p=>dist(apply(reg,p.scan),p.bim)),inl=[];errs.forEach((e,k)=>{if(e<=threshold)inl.push(k);});
  const sse=inl.reduce((s,k)=>s+errs[k]**2,0);
  if(!best||inl.length>best.count||(inl.length===best.count&&-sse>-best.sse))best={count:inl.length,sse,inliers:inl};
 }
 if(!best||best.inliers.length<3)throw new Error('RANSAC found no consensus of 3+ pairs within '+threshold.toFixed(2)+' m');
 let inliers=best.inliers;
 for(let it=0;it<3;it++){const reg=fitYawTranslation(inliers.map(k=>pairs[k])),next=[];pairs.forEach((p,k)=>{if(dist(apply(reg,p.scan),p.bim)<=threshold)next.push(k);});if(next.join()===inliers.join()||next.length<3)break;inliers=next;}
 return{inliers,outliers:pairs.map((_,k)=>k).filter(k=>!inliers.includes(k)),thresholdMetres:threshold};
}
const azimuth=v=>Math.atan2(v[2],v[0]);
/* Python's (a+pi) % (2pi) - pi with floor-mod semantics */
const wrap=a=>{const m=2*Math.PI;return ((a+Math.PI)%m+m)%m-Math.PI;};
/* Heading offset (deg) about +Y to pre-multiply onto the photo sphere so clicked photo features hit BIM targets.
   photoDirections: scan-frame directions of clicked photo pixels with NO heading offset applied. */
function solveHeading(obs,reg){
 const dirs=obs.photoDirections||[],targets=obs.bimTargets||[];
 if(dirs.length!==targets.length||dirs.length<2)throw new Error('Heading needs 2+ photo directions with matching BIM targets');
 const st=vec(obs.stationPosition),deltas=[],elev=[];
 dirs.forEach((d,i)=>{vec(d);const ts=invert(reg,vec(targets[i])),v=[ts[0]-st[0],ts[1]-st[1],ts[2]-st[2]];
  if(Math.hypot(v[0],v[2])<.3||Math.hypot(d[0],d[2])<1e-6)throw new Error('Heading targets must not be straight above/below the station');
  deltas.push(wrap(azimuth(d)-azimuth(v)));elev.push((Math.atan2(d[1],Math.hypot(d[0],d[2]))-Math.atan2(v[1],Math.hypot(v[0],v[2])))*R2D);});
 const delta=Math.atan2(deltas.reduce((s,x)=>s+Math.sin(x),0),deltas.reduce((s,x)=>s+Math.cos(x),0));
 return{station:obs.station,headingOffsetDegrees:delta*R2D,residualsDegrees:deltas.map(x=>Math.abs(wrap(x-delta)*R2D)),elevationResidualsDegrees:elev,observations:deltas.length};
}
function splitPairs(data){
 const pairs=data.pairs||[],ids=new Set();
 for(const p of pairs){vec(p.scan);vec(p.bim);if(p.role!=='fit'&&p.role!=='check')throw new Error('Each pair needs role "fit" or "check"');const id=String(p.id??'');if(!id||ids.has(id))throw new Error('Pair ids must be unique and non-empty');ids.add(id);}
 const fit=pairs.filter(p=>p.role==='fit'),checks=pairs.filter(p=>p.role==='check');
 if(fit.length<MIN_FIT_PAIRS)throw new Error('Need '+MIN_FIT_PAIRS+'+ fit pairs (got '+fit.length+')');
 if(!checks.length)throw new Error('Need 1+ independent check pair, never used in the fit');
 for(const c of checks)for(const p of fit)if(dist(c.scan,p.scan)<1e-6||dist(c.bim,p.bim)<1e-6)throw new Error('Check '+c.id+' reuses a fit landmark; checks must be independent');
 return{fit,checks};
}
function solve(data){
 const {fit,checks}=splitPairs(data),rs=data.ransac||{};let inliers,ransacOut;
 if(rs.enabled){const r=ransac(fit,Number(rs.thresholdMetres??.25));inliers=r.inliers;ransacOut={enabled:true,thresholdMetres:r.thresholdMetres,outlierIds:r.outliers.map(k=>fit[k].id)};}
 else{inliers=fit.map((_,k)=>k);ransacOut={enabled:false,outlierIds:[]};}
 const used=inliers.map(k=>fit[k]);if(used.length<3)throw new Error('Fewer than 3 inlier fit pairs remain');
 const f=fitYawTranslation(used),reg={rotationYDegrees:f.rotationYDegrees,translation:f.translation};
 const fitRows=residualRows(reg,fit,new Set(inliers)),checkRows=residualRows(reg,checks);
 return{...reg,scale:1,
  fit:{pairs:used.length,residuals:fitRows,...stats(fitRows.filter(r=>r.inlier).map(r=>r.errorMetres))},
  leaveOneOut:leaveOneOut(used),
  checks:{pairs:checks.length,surveyed:checks.every(c=>!!c.surveyed),residuals:checkRows,...stats(checkRows.map(r=>r.errorMetres))},
  ransac:ransacOut,headings:(data.headingObservations||[]).map(o=>solveHeading(o,reg))};
}
const f6=v=>v.map(x=>x.toFixed(6)).join(',');
function canonicalPairsText(data){
 const lines=(data.pairs||[]).map(p=>[p.role,p.id,f6(p.scan),f6(p.bim),p.surveyed?'surveyed':'unsurveyed'].join('|'));
 for(const o of data.headingObservations||[])lines.push(['heading',o.station,f6(o.stationPosition),o.photoDirections.map(f6).join(';'),o.bimTargets.map(f6).join(';')].join('|'));
 return lines.join('\n')+'\n';
}
async function sha256Hex(text){const c=(typeof globalThis!=='undefined'&&globalThis.crypto)||null;if(!c?.subtle)return null;const buf=await c.subtle.digest('SHA-256',new TextEncoder().encode(text));return[...new Uint8Array(buf)].map(b=>b.toString(16).padStart(2,'0')).join('');}
/* slider-only heading offsets (visual alignment without picks); recorded separately, pick-based solves win */
function manualOffsets(data){const out={};for(const [k,v] of Object.entries(data.manualHeadingOffsetsDegrees||{})){if(typeof v!=='number'||!Number.isFinite(v)||Math.abs(v)>180)throw new Error('Manual heading offsets must be finite degrees within +/-180');out[String(k)]=v;}return out;}
const statusFor=r=>r.checks.surveyed?'landmark-fit-surveyed-checks':'landmark-fit-unsurveyed';
async function buildExport(data,result,{created,extraInputs}={}){
 const status=statusFor(result);
 return{schema:SCHEMA,capture:data.capture,createdAt:created||new Date().toISOString().replace(/\.\d{3}Z$/,'Z'),
  rotationYDegrees:result.rotationYDegrees,translation:result.translation,scale:1,status,
  method:{model:'rigid yaw about +Y + XYZ translation, scale fixed at 1',solver:'closed-form centroid / atan2 (same as scripts/capture_import.py fit and the accepted ICP update step)',ransac:result.ransac,icp:null},
  frames:{source:'scan viewer frame, Y-up metres (photo stations and scan mesh)',target:'BIM viewer world, Y-up metres'},
  inputs:{pairsSha256:await sha256Hex(canonicalPairsText(data)),baseline:data.baseline??null,...(extraInputs||{})},
  fit:result.fit,leaveOneOut:result.leaveOneOut,checks:result.checks,
  stationHeadingOffsetsDegrees:{...manualOffsets(data),...Object.fromEntries(result.headings.filter(h=>h.station).map(h=>[h.station,h.headingOffsetDegrees]))},
  manualHeadingOffsetsDegrees:manualOffsets(data),
  headingSolves:result.headings,pairs:data.pairs,headingObservations:data.headingObservations||[],
  scope:'Visualization candidate from clicked landmarks. Fit and leave-one-out residuals are internal consistency; '+(status.endsWith('surveyed-checks')?'check points are marked surveyed by the author.':'check points are not surveyed, so this is not surveyed accuracy.')+' Review in scan-compare.html?registration=<this file> before publishing.'};
}
function assertCandidateName(p){const base=String(p).split('/').pop();if(base==='registration.json'||base==='accepted-registration.json')throw new Error('Refusing to replace an accepted/provisional registration; save a new dated candidate');return p;}
function suggestFilename(capture,date){return assertCandidateName('registration-candidates/'+date+'-landmark-fit.json');}
/* ?registration=<path>: same-origin, relative, .json only, no traversal */
function safeRegistrationPath(raw){if(typeof raw!=='string')return null;return /^(?!\/)(?!.*\.\.)(?!.*\/\/)[A-Za-z0-9_\-./]+\.json$/.test(raw)?raw:null;}
function validateRegistration(r,capture){
 const fail=reason=>({ok:false,reason});
 if(!r||r.schema!==SCHEMA)return fail('not a registration candidate');
 if(!CANDIDATE_STATUSES.includes(r.status))return fail('unknown candidate status');
 if(r.capture!==capture)return fail('candidate belongs to capture '+r.capture);
 if(!Number.isFinite(r.rotationYDegrees)||!Array.isArray(r.translation)||r.translation.length!==3||!r.translation.every(Number.isFinite))return fail('invalid transform');
 if(r.scale!==undefined&&r.scale!==1)return fail('scale must be 1');
 const h=r.stationHeadingOffsetsDegrees||{};if(typeof h!=='object'||!Object.values(h).every(v=>Number.isFinite(v)&&Math.abs(v)<=180))return fail('invalid heading offsets');
 return{ok:true};
}
return{SCHEMA,PAIRS_SCHEMA,MIN_FIT_PAIRS,CANDIDATE_STATUSES,apply,invert,rotateY,fitYawTranslation,leaveOneOut,ransac,solveHeading,splitPairs,solve,canonicalPairsText,sha256Hex,buildExport,assertCandidateName,suggestFilename,safeRegistrationPath,validateRegistration,residualRows,stats};
});
