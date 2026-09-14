"""Package an optimized Gaussian PLY for local browser review; never publish.
Mobile derivative preserves selected optimized XYZ, quaternion, scale, opacity
and DC color, dropping higher spherical harmonics and limiting point count.
"""
import argparse,hashlib,json,shutil
from pathlib import Path
import numpy as np

def read_ply(path):
    fields=[];count=None
    with Path(path).open('rb')as f:
        if f.readline()!=b'ply\n':raise ValueError('Expected PLY')
        for _ in range(150):
            line=f.readline().decode('ascii').strip()
            if line.startswith('format ')and line!='format binary_little_endian 1.0':raise ValueError('Only binary little endian PLY supported')
            if line.startswith('element vertex '):count=int(line.split()[-1])
            elif line.startswith('element '):raise ValueError('Unexpected non-vertex element')
            if line.startswith('property '):
                _,kind,name=line.split()
                if kind!='float':raise ValueError('Expected float Gaussian parameters')
                fields.append((name,'<f4'))
            if line=='end_header':break
        else:raise ValueError('Invalid PLY header')
        if not count or count>3000000:raise ValueError('Invalid/excessive Gaussian count for review')
        dtype=np.dtype(fields);raw=f.read()
        if len(raw)!=count*dtype.itemsize:raise ValueError('Incomplete Gaussian PLY')
        data=np.frombuffer(raw,dtype=dtype).copy()
    required=['x','y','z','opacity']+[f'{k}_{i}'for k,n in [('rot',4),('scale',3),('f_dc',3)]for i in range(n)]
    if any(k not in data.dtype.names for k in required):raise ValueError('Not an optimized Gaussian PLY')
    if not all(np.isfinite(data[k]).all()for k in data.dtype.names):raise ValueError('Non-finite optimized parameters')
    norms=np.sqrt(sum(data[f'rot_{i}']**2 for i in range(4)))
    if np.any(norms<1e-6):raise ValueError('Zero Gaussian rotation quaternion')
    return data

def mobile_subset(data,budget=350000):
    if budget<1:raise ValueError('Positive mobile budget required')
    alpha=1/(1+np.exp(-np.clip(data['opacity'],-80,80)));eligible=np.flatnonzero(alpha>=.02)
    if not len(eligible):raise ValueError('No visible optimized Gaussians')
    if len(eligible)>budget:
        xyz=np.column_stack([data[k][eligible]for k in ['x','y','z']]);cells=np.floor(xyz/.15).astype(np.int64)
        # One high-opacity representative per 15 cm spatial cell, then fill
        # by opacity. This is an explicit lossy preview, not a retrained scene.
        order=np.argsort(-alpha[eligible],kind='stable');_,first=np.unique(cells[order],axis=0,return_index=True);cover=eligible[order[first]]
        if len(cover)>budget:
            rng=np.random.default_rng(42);chosen=rng.choice(cover,budget,replace=False)
        else:
            remaining=np.setdiff1d(eligible,cover,assume_unique=False);rest=remaining[np.argsort(-alpha[remaining],kind='stable')[:budget-len(cover)]];chosen=np.concatenate([cover,rest])
    else:chosen=eligible
    names=[n for n in data.dtype.names if not n.startswith('f_rest_')]
    out=np.empty(len(chosen),dtype=[(n,'<f4')for n in names])
    for name in names:out[name]=data[name][chosen]
    return out

def write_ply(path,data):
    header='ply\nformat binary_little_endian 1.0\ncomment Gaussian mobile preview; SH0; optimized parameter subset\nelement vertex '+str(len(data))+'\n'+''.join('property float '+n+'\n'for n in data.dtype.names)+'end_header\n'
    with Path(path).open('wb')as f:f.write(header.encode());f.write(data.tobytes())

def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()

def package(source,output,panoramas,station_id,mobile_budget=350000,iterations=None,desktop_ksplat=None):
    source,output=Path(source),Path(output)
    if output.exists():raise FileExistsError('Use a new output folder')
    data=read_ply(source);mobile=mobile_subset(data,mobile_budget)
    source_sha=sha(source);desktop_source=source;desktop_name='trained.ply';desktop_count=len(data);encoding='Byte-identical optimized PLY'
    if desktop_ksplat:
        desktop_source=Path(desktop_ksplat)
        encoded=json.loads(Path(str(desktop_source)+'.json').read_text())
        if desktop_source.suffix.lower()!='.ksplat' or encoded.get('sourceSha256')!=source_sha or encoded.get('outputSha256')!=sha(desktop_source):raise ValueError('Compressed derivative hashes do not bind to this checkpoint')
        desktop_count=encoded.get('splatCount')
        if encoded.get('sourceCount')!=len(data) or type(desktop_count)is not int or not 0<desktop_count<=len(data):raise ValueError('Compressed derivative count mismatch')
        desktop_name='trained.ksplat';encoding=encoded.get('method','Lossy KSplat derivative')
    m=json.loads(Path(panoramas).read_text());s=next(s for s in m['stations']if s['id']==station_id)
    # Same initial yaw as the verified panorama view, derived from E57 +X.
    from prepare_gaussian_dataset import camera_to_world
    from scipy.spatial.transform import Rotation
    camera={'position':s['position'],'quaternion':Rotation.from_matrix(camera_to_world(s,0,0)[:3,:3]).as_quat().tolist(),'fov':65,'zoom':1}
    output.mkdir(parents=True);shutil.copyfile(desktop_source,output/desktop_name);write_ply(output/'mobile.ply',mobile)
    report={'status':'experimental-trained','frame':'scan-y-up-metres','file':desktop_name,'mobileFile':'mobile.ply','splatCount':desktop_count,'mobileSplatCount':len(mobile),'camera':camera,'maxDistance':120,
      'provenance':{'trainingIterations':iterations,'sourceCheckpointSha256':source_sha,'sourceCheckpointBytes':source.stat().st_size,'sourceGaussianCount':len(data),'desktopEncoding':encoding,'desktopSha256':sha(output/desktop_name),'mobileSha256':sha(output/'mobile.ply'),'desktopBytes':(output/desktop_name).stat().st_size,'mobileBytes':(output/'mobile.ply').stat().st_size,'initialStation':station_id,'mobileMethod':'SH0; opacity >=0.02; 15cm cell coverage and opacity budget. Lossy visual derivative; no change to source checkpoint.','geometryScope':'Trained appearance, not surveyed geometry or device identity. Same Cupix scan frame must be verified.'}}
    (output/'viewer.json').write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--panoramas',type=Path,required=True);p.add_argument('--station-id',required=True);p.add_argument('--mobile-budget',type=int,default=350000);p.add_argument('--iterations',type=int);p.add_argument('--desktop-ksplat',type=Path);a=p.parse_args();print(json.dumps(package(a.input,a.output,a.panoramas,a.station_id,a.mobile_budget,a.iterations,a.desktop_ksplat),indent=2))
