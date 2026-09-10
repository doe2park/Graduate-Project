exec(open('/tmp/register-scan.py').read().split('j=json.load')[0])
j=json.load(open('/private/tmp/scan-reference-surfaces.json'));R=np.array(j['reference']);S=np.load('/private/tmp/full-scan.npz')['points'];R=R[(R[:,1]>4.7)&(R[:,1]<10)];S=S[(S[:,1]>3.5)&(S[:,1]<7.6)];R=R[np.unique(np.round(R/.14).astype(int),axis=0,return_index=True)[1]];S=S[np.unique(np.round(S/.18).astype(int),axis=0,return_index=True)[1]][::2];tree=cKDTree(R)
exec(open('/tmp/register-scan.py').read().split('def mat(a):')[1].split('a0=')[0].join(['def mat(a):','']))
c=json.load(open('/private/tmp/full-refined-registration.json'))['candidates'][0];a0=np.radians(c['rotationYDegrees']);t0=np.array(c['translation']);center=np.median(S[:,[0,2]],axis=0);zones=(S[:,0]>center[0]).astype(int)+2*(S[:,2]>center[1]).astype(int);folds=[]
for zone in range(4):
 train=S[zones!=zone];test=S[zones==zone];a,t,m=fit(a0,t0);folds.append({'heldOutZone':zone,'points':len(test),'rotationYDegrees':float(np.degrees(a)),'translation':t.tolist(),'translationShiftMetres':float(np.linalg.norm(t-t0)),**m})
print(json.dumps(folds,indent=2));json.dump(folds,open('/private/tmp/full-spatial-validation.json','w'),indent=2)
