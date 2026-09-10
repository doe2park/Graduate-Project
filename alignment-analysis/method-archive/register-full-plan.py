exec(open('/tmp/register-scan.py').read().split('j=json.load')[0])
j=json.load(open('/private/tmp/scan-reference-surfaces.json'));r=np.array(j['reference']);s=np.load('/private/tmp/full-scan.npz')['walls'];r=r[(r[:,1]>6.5)&(r[:,1]<7.5)][:,[0,2]];s=s[(s[:,1]>5)&(s[:,1]<6)][:,[0,2]]
r=r[np.unique(np.round(r/.12).astype(int),axis=0,return_index=True)[1]];s=s[np.unique(np.round(s/.15).astype(int),axis=0,return_index=True)[1]];s=s[::max(1,len(s)//1600)];tree=cKDTree(r)
def m(a):return np.array([[np.cos(a),np.sin(a)],[-np.sin(a),np.cos(a)]])
def fit(a,t):
 for it in range(55):
  x=s@m(a).T+t;d,ix=tree.query(x);keep=d<np.quantile(d,.8);A=s[keep];B=r[ix[keep]];ca=A.mean(0);cb=B.mean(0);A-=ca;B-=cb;a=np.arctan2(np.sum(A[:,1]*B[:,0]-A[:,0]*B[:,1]),np.sum(A*B));t=cb-m(a)@ca
 d,_=tree.query(s@m(a).T+t);return {'yaw':float(np.degrees(a)),'xz':t.tolist(),'median':float(np.median(d)),'p80':float(np.quantile(d,.8)),'within025':float(np.mean(d<.25))}
res=[]
for yaw in [-180,-135,-90,-45,0,45,90,135]:
 for x in [-20,-10,0,10,20]:
  for z in [-15,-5,5,15]:
   a=np.radians(yaw);t=np.array([x,z])-m(a)@s.mean(0);res.append(fit(a,t))
res.sort(key=lambda x:x['p80']);print(json.dumps(res[:12],indent=2));json.dump(res,open('/private/tmp/full-plan-registration-candidates.json','w'),indent=2)
