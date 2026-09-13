"""Perspective views from E57 spherical panoramas; preserves scan Y-up metre frame.
Requires numpy, scipy, Pillow. Source manifests from captured panorama intake.
"""
import argparse, hashlib, io, json, math, struct
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from scipy.spatial.transform import Rotation

W=np.array([[1.,0,0],[0,0,1],[0,-1,0]])

def face_rotation(yaw,pitch):
    a,b=np.deg2rad([yaw,pitch]);forward=np.array([np.cos(a)*np.cos(b),np.sin(a)*np.cos(b),np.sin(b)])
    right=np.array([np.sin(a),-np.cos(a),0]);up=np.cross(right,forward)
    return np.column_stack([right,up,-forward])

def camera_to_world(station,yaw,pitch):
    m=np.eye(4);m[:3,:3]=W@Rotation.from_quat(station['e57Quaternion']).as_matrix()@face_rotation(yaw,pitch);m[:3,3]=station['position'];return m

def sphere_uv(directions):
    d=directions/np.linalg.norm(directions,axis=-1,keepdims=True)
    return np.stack([(.5-np.arctan2(d[...,1],d[...,0])/(2*np.pi))%1,.5-np.arcsin(np.clip(d[...,2],-1,1))/np.pi],axis=-1)

def perspective(image,yaw,pitch,size=640,fov=100):
    focal=size/(2*np.tan(np.deg2rad(fov)/2));y,x=np.mgrid[:size,:size]
    rays=np.stack([(x+.5-size/2)/focal,-(y+.5-size/2)/focal,-np.ones_like(x)],axis=-1)
    uv=sphere_uv(rays@face_rotation(yaw,pitch).T);arr=np.asarray(image.convert('RGB'));h,w=arr.shape[:2]
    # Wrap longitude with a one-pixel halo, clamp only at poles.
    arr=np.concatenate([arr[:,-1:],arr,arr[:,:1]],axis=1);coords=[np.clip(uv[...,1]*h-.5,0,h-1),uv[...,0]*w+.5]
    return Image.fromarray(np.stack([map_coordinates(arr[...,k],coords,order=1,mode='nearest')for k in range(3)],axis=-1).astype('uint8'))

def read_glb(path):
    with Path(path).open('rb')as f:
        magic,version,total=struct.unpack('<4sII',f.read(12));assert magic==b'glTF'and version==2
        n,t=struct.unpack('<II',f.read(8));j=json.loads(f.read(n));n,t=struct.unpack('<II',f.read(8));data=f.read(n)
    return j,data

def mesh_seed(paths,center,radius,count,seed=42,up_axis="z"):
    if up_axis not in ("z","y"):raise ValueError("Seed up axis must be z or y")
    basis=W if up_axis=="z" else np.eye(3)
    """Sample texture-bearing exported scan geometry, not BIM; never rewrite GLBs."""
    rng=np.random.default_rng(seed);points=[];colors=[];weights=[]
    for path in paths:
        j,data=read_glb(path)
        def accessor(index):
            a=j['accessors'][index];v=j['bufferViews'][a['bufferView']];n={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];dtype={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']];item=np.dtype(dtype).itemsize
            return np.ndarray((a['count'],n),dtype=dtype,buffer=data,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',item*n),item)).copy()
        textures={}
        def texture(index):
            im_index=j['textures'][index]['source']
            if im_index not in textures:
                v=j['bufferViews'][j['images'][im_index]['bufferView']];b=v.get('byteOffset',0);textures[im_index]=np.asarray(Image.open(io.BytesIO(data[b:b+v['byteLength']])).convert('RGB'))
            return textures[im_index]
        def walk(index,parent):
            node=j['nodes'][index]
            if 'matrix'in node:m=np.array(node['matrix']).reshape((4,4),order='F')
            else:
                m=np.eye(4);m[:3,:3]=Rotation.from_quat(node.get('rotation',[0,0,0,1])).as_matrix()@np.diag(node.get('scale',[1,1,1]));m[:3,3]=node.get('translation',[0,0,0])
            world=parent@m
            if 'mesh'in node:
                for primitive in j['meshes'][node['mesh']]['primitives']:
                    if primitive.get('mode',4)!=4:continue
                    verts=accessor(primitive['attributes']['POSITION']);verts=(verts@world[:3,:3].T+world[:3,3])@basis.T
                    ids=accessor(primitive['indices']).reshape(-1,3).astype(int);tri=verts[ids]
                    mid=tri.mean(axis=1);keep=np.linalg.norm(mid[:,[0,2]]-np.array(center)[[0,2]],axis=1)<radius
                    keep&=(mid[:,1]>center[1]-3)&(mid[:,1]<center[1]+7)
                    ids=ids[keep];tri=tri[keep]
                    if not len(tri):continue
                    area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)/2
                    good=area>1e-9;ids=ids[good];tri=tri[good];area=area[good]
                    if not len(tri):continue
                    n=min(20000,max(200,int(area.sum()*70)));pick=rng.choice(len(tri),n,p=area/area.sum());a=np.sqrt(rng.random(n));b=rng.random(n);bary=np.stack([1-a,a*(1-b),a*b],axis=1)
                    pts=(tri[pick]*bary[...,None]).sum(axis=1);rgb=np.full((n,3),128,dtype=np.uint8)
                    mat=j.get('materials',[])[primitive.get('material',0)].get('pbrMetallicRoughness',{})
                    if 'baseColorTexture'in mat and 'TEXCOORD_0'in primitive['attributes']:
                        uv=accessor(primitive['attributes']['TEXCOORD_0']);uv=(uv[ids[pick]]*bary[...,None]).sum(axis=1);im=texture(mat['baseColorTexture']['index']);h,w=im.shape[:2];rgb=im[np.clip((uv[:,1]*h).astype(int),0,h-1),np.clip((uv[:,0]*w).astype(int),0,w-1)]
                    points.append(pts);colors.append(rgb);weights.append(np.full(n,area.sum()/n))
            for child in node.get('children',[]):walk(child,world)
        for node in j['scenes'][j.get('scene',0)]['nodes']:walk(node,np.eye(4))
    if not points:raise ValueError('No scan seed geometry within pilot area')
    xyz=np.concatenate(points);rgb=np.concatenate(colors);w=np.concatenate(weights);n=min(count,len(xyz));i=rng.choice(len(xyz),n,replace=False,p=w/w.sum());return xyz[i],rgb[i]

def save_points(path,xyz,rgb):
    # Brush imports RGB point clouds and initializes Gaussian covariance from neighbors.
    header=f'ply\nformat binary_little_endian 1.0\nelement vertex {len(xyz)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n'
    data=np.empty(len(xyz),dtype=[('xyz','<f4',(3,)),('rgb','u1',(3,))]);data['xyz']=xyz;data['rgb']=rgb
    with Path(path).open('wb')as f:f.write(header.encode());f.write(data.tobytes())

def build(manifest,output,center_id,radius,size=640,seed_glbs=(),point_count=50000,seed_up_axis="z"):
    if not math.isfinite(radius) or radius<=0:raise ValueError("Positive finite radius required")
    if not 64<=size<=2048 or not 1<=point_count<=1000000:raise ValueError("Invalid local training size or seed count")
    if seed_up_axis not in ("z","y"):raise ValueError("Seed up axis must be z or y")
    manifest=Path(manifest).resolve();out=Path(output).resolve()
    if out.exists():raise FileExistsError('Use a new dataset output directory')
    m=json.loads(manifest.read_text());stations=m['stations'];center=next(s for s in stations if s['id']==center_id)['position'];selected=[s for s in stations if np.linalg.norm(np.array(s['position'])-center)<=radius]
    if len(selected)<4:raise ValueError('Pilot needs at least 4 captured stations')
    out.mkdir(parents=True);(out/'images').mkdir();train=[];test=[];provenance=[]
    faces=[(a,0)for a in [0,90,180,270]]+[(a,b)for a in [45,225]for b in [-55,55]]
    for i,s in enumerate(selected):
        src=manifest.parent/s['file'];sha=hashlib.sha256(src.read_bytes()).hexdigest()
        if sha!=s['sha256']:raise ValueError('Source image hash changed')
        image=Image.open(src);is_test=i%7==3
        provenance.append({'id':s['id'],'sha256':sha,'split':'evaluation'if is_test else'train'})
        for k,(yaw,pitch)in enumerate(faces):
            file=f'images/{i:03d}_{k}.png';perspective(image,yaw,pitch,size).save(out/file)
            frame={'file_path':file,'transform_matrix':camera_to_world(s,yaw,pitch).tolist()};(test if is_test else train).append(frame)
        image.close()
    common={'camera_model':'OPENCV','w':size,'h':size,'fl_x':size/(2*math.tan(math.radians(50))),'fl_y':size/(2*math.tan(math.radians(50))),'cx':size/2,'cy':size/2}
    if seed_glbs:
        xyz,rgb=mesh_seed(seed_glbs,center,radius+9,point_count,up_axis=seed_up_axis);save_points(out/'scan-seed.ply',xyz,rgb);common['ply_file_path']='scan-seed.ply'
    for name,frames in [('transforms.json',train),('transforms_val.json',test)]:
        (out/name).write_text(json.dumps({**common,'frames':frames},indent=2))
    report={'status':'dataset-prepared-not-trained','sourceManifestSha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'centerId':center_id,'center':center,'radiusMetres':radius,'stations':provenance,'trainViews':len(train),'evaluationViews':len(test),'faceSize':size,'horizontalFovDegrees':100,'frame':'unchanged scan Y-up metres','seed':'sampled exported scan mesh, not BIM'if seed_glbs else'random trainer initialization','seedInputUpAxis':seed_up_axis,'seedSourceHashes':{Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest()for p in seed_glbs},'evaluationScope':'Held-out images by station; camera poses and mesh initialization originate from same Cupix reconstruction, so not independent geometry validation.'}
    (out/'dataset-provenance.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items()if k!='stations'},indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--center-id',required=True);p.add_argument('--radius',type=float,default=9);p.add_argument('--size',type=int,default=640);p.add_argument('--seed-glb',type=Path,action='append',default=[]);p.add_argument('--point-count',type=int,default=50000);p.add_argument('--seed-up-axis',choices=['z','y'],default='z');a=p.parse_args();build(a.manifest,a.output,a.center_id,a.radius,a.size,a.seed_glb,a.point_count,a.seed_up_axis)
