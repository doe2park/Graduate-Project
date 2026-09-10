import sys,json,numpy as np
sys.path.insert(0,'/private/tmp/grimes-registration-deps')
from scipy.spatial import cKDTree
j=json.load(open('/private/tmp/scan-reference-points.json'));R=np.array(j['reference']);S=np.array(j['scan'])
# Restrict reference to physical level 1 height band; preserve spatial spread.
R=R[(R[:,1]>4.7)&(R[:,1]<10)];R=R[np.unique(np.round(R/.12).astype(int),axis=0,return_index=True)[1]]
S=S[np.unique(np.round(S/.12).astype(int),axis=0,return_index=True)[1]];train=S[::2];test=S[1::2];tree=cKDTree(R)
def mat(a):
 c=np.cos(a);s=np.sin(a);return np.array([[c,0,s],[0,1,0],[-s,0,c]])
def metric(a,t):
 d,_=tree.query(test@mat(a).T+t);return {'median':float(np.median(d)),'p80':float(np.quantile(d,.8)),'within025':float(np.mean(d<.25)),'within05':float(np.mean(d<.5))}
def fit(a,t):
 for it in range(40):
  X=train@mat(a).T+t;d,ix=tree.query(X);mask=(d<min(2,np.quantile(d,.65)));A=train[mask];B=R[ix[mask]]
  if len(A)<100:break
  ca=A.mean(0);cb=B.mean(0);A=A-ca;B=B-cb
  anew=np.arctan2(np.sum(A[:,2]*B[:,0]-A[:,0]*B[:,2]),np.sum(A[:,0]*B[:,0]+A[:,2]*B[:,2]));tnew=cb-mat(anew)@ca
  delta=np.linalg.norm(tnew-t)+abs(anew-a);a,t=anew,tnew
  if delta<1e-5:break
 return a,t,metric(a,t)
a0=np.radians(-135);t0=np.array([16.9,1.524,10.8]);initial=metric(a0,t0);print('initial',initial,flush=True)
results=[]
for yaw in [-150,-142.5,-135,-127.5,-120]:
 for dx,dz in [(0,0),(-3,0),(3,0),(0,-3),(0,3)]:
  a,t,m=fit(np.radians(yaw),t0+[dx,0,dz]);results.append({'yaw':float(np.degrees(a)),'translation':t.tolist(),**m})
results.sort(key=lambda v:v['median']);out={'method':'trimmed point-to-point rigid yaw/translation ICP, alternating-voxel holdout. Geometry consistency only; no survey anchors.','referencePoints':len(R),'scanPoints':len(S),'initial':initial,'candidates':results[:8]};json.dump(out,open('/private/tmp/scan-registration-analysis.json','w'),indent=2);print(json.dumps(out,indent=2))
