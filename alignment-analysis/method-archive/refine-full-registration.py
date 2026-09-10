exec(open('/tmp/register-scan.py').read().split('j=json.load')[0])
j=json.load(open('/private/tmp/scan-reference-surfaces.json'));R=np.array(j['reference']);S=np.load('/private/tmp/full-scan.npz')['points'];R=R[(R[:,1]>4.7)&(R[:,1]<10)];S=S[(S[:,1]>3.5)&(S[:,1]<7.6)];R=R[np.unique(np.round(R/.12).astype(int),axis=0,return_index=True)[1]];S=S[np.unique(np.round(S/.14).astype(int),axis=0,return_index=True)[1]];train=S[::3];test=S[1::3];tree=cKDTree(R)
exec(open('/tmp/register-scan.py').read().split('def mat(a):')[1].split('a0=')[0].join(['def mat(a):','']))
res=[]
for y in [0,.5,1,1.5,2]:
 a,t,metric0=fit(np.radians(.2),np.array([-35.23,y,-25.086]));res.append({'rotationYDegrees':float(np.degrees(a)),'translation':t.tolist(),**metric0})
res.sort(key=lambda r:r['p80']);out={'candidates':res,'trainPoints':len(train),'holdoutPoints':len(test)};json.dump(out,open('/private/tmp/full-refined-registration.json','w'),indent=2);print(json.dumps(out,indent=2))
