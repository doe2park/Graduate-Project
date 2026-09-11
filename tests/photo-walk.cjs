const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const s=fs.readFileSync(require('node:path').join(__dirname,'../scan-photo.html'),'utf8');const fn=s.match(/function chooseWalkNeighbor\([\s\S]*?\n}/);assert.ok(fn,'directional route selector exists');const choose=vm.runInNewContext(fn[0]+';chooseWalkNeighbor');
const stations=[{position:[0,0,0],neighbors:[1,2,3]},{position:[0,0,-2]},{position:[0,0,2]},{position:[0,0,-12]},{position:[0,0,-1]}];
assert.equal(choose(stations,0,[0,0,-1]),1);assert.equal(choose(stations,0,[0,0,1]),2);assert.equal(choose(stations,0,[1,0,0]),-1);console.log('PASS directional selection, distance bound and no off-route shortcuts');
