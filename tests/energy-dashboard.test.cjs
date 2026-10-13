const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test');
const html=fs.readFileSync('campus-energy-dashboard.html','utf8');
const source=html.match(/<script id="energy-model">([\s\S]*?)<\/script>/)?.[1]||'';
const c={Intl,Date};vm.createContext(c);vm.runInContext(source,c);
test('Pacific observations convert independently of machine timezone, DST ambiguity is unavailable',()=>{
 assert.equal(typeof c.observedTime,'function');
 assert.equal(c.observedTime('2026-10-12 18:45:01'),Date.parse('2026-10-13T01:45:01Z'));
 assert.equal(c.observedTime('2026-01-12 18:45:01'),Date.parse('2026-01-13T02:45:01Z'));
 assert.equal(c.observedTime('2026-11-01 01:30:00'),null);
 assert.equal(c.observedTime('2026-03-08 02:30:00'),null);
 assert.equal(c.observedTime('2026-02-30 12:00:00'),null);
});
test('history sorts full observation dates, preserves zero, excludes missing/invalid, deduplicates observations',()=>{
 assert.equal(typeof c.series,'function');
 const p=c.series([{ts:'2026-10-12 18:00:00',t:'01:00',kw:0},{ts:'2026-10-11 18:00:00',t:'23:00',kw:8},{ts:'2026-10-12 18:00:00',kw:0},{ts:'2026-10-12 17:00:00',kw:null},{ts:'bad',kw:9}]);
 assert.equal(p.length,2);assert.equal(p[0].kw,8);assert.equal(p[1].kw,0);
});
test('period uses elapsed observation time, not a last-96 assumption; no-data statistics stay null',()=>{
 assert.equal(typeof c.windowSeries,'function');const now=Date.parse('2026-10-13T01:00:00Z');
 const p=[{x:now-2*86400000,kw:10},{x:now-3600000,kw:0}];
 assert.equal(c.windowSeries(p,24,now).length,1);assert.equal(c.summarize([]).mean,null);assert.equal(c.summarize([p[1]]).mean,0);
});
test('data age is explicit without an arbitrary stale classification',()=>{
 assert.equal(typeof c.freshness,'function');const now=Date.parse('2026-10-13T02:00:00Z');
 assert.equal(c.freshness({kw:0,timestamp:'2026-10-12 18:45:00'},now).label,'15 minutes ago');
 assert.equal(c.freshness({kw:10,timestamp:'2026-10-11 18:45:00'},now).label,'1 day ago');
 assert.equal(c.freshness({kw:null,timestamp:'2026-10-12 18:45:00'},now).label,'No reading');
 assert.equal(c.freshness({kw:10,timestamp:'2026-10-14 18:45:00'},now).label,'Time unknown');
});
test('CSV retains source observations and units, quotes cells and neutralizes formula text',()=>{
 assert.equal(typeof c.exportCSV,'function');
 const csv=c.exportCSV('g',{name:'=HYPERLINK("x")',meter:'3+76+77'},[{x:1,ts:'2026-10-12 18:45:01',kw:0}]);
 assert.match(csv,/America\/Los_Angeles/);assert.match(csv,/kW/);assert.match(csv,/0/);assert.match(csv,/'=HYPERLINK/);
});
test('empty chart is unavailable, but a populated comparison is still shown',()=>{
 assert.equal(typeof c.hasObservations,'function');
 assert.equal(c.hasObservations([],[]),false);assert.equal(c.hasObservations([],[{x:1,kw:0}]),true);
});
test('interpretation compares observations only with enough comparable samples',()=>{
 assert.equal(typeof c.interpretation,'function');const now=Date.parse('2026-10-13T02:00:00Z');
 const b={kw:100,timestamp:'2026-10-12 18:45:00'},points=[{x:now-1800000,kw:50},{x:now-900000,kw:100}];
 const r=c.interpretation(b,points,now);assert.equal(r.kind,'observed');assert.equal(r.difference,50);assert.equal(r.previous.kw,50);
 assert.equal(c.interpretation(b,[points[1]],now).kind,'insufficient');
 assert.equal(c.interpretation({kw:0,timestamp:b.timestamp},[{x:now-1800000,kw:0},{x:now-900000,kw:0}],now).difference,0);
});
test('interpretation does not diagnose old data and handles unavailable timestamps',()=>{
 const now=Date.parse('2026-10-13T02:00:00Z'),points=[{x:now-10000,kw:10},{x:now-5000,kw:20}];
 assert.equal(c.interpretation({kw:null},points,now).kind,'missing');
 assert.equal(c.interpretation({kw:100,timestamp:'2026-10-11 18:45:00'},points,now).kind,'insufficient');
 assert.equal(c.interpretation({kw:100,timestamp:'bad'},points,now).kind,'unknown');
 assert.equal(c.interpretation({kw:100,timestamp:'2026-10-12 18:45:00'},[],now).kind,'insufficient');
});

test('sampling context reports irregular cadence and real observation dates, not completeness',()=>{
 assert.equal(typeof c.sampling,'function');
 const p=[{x:0,kw:0,ts:'2026-10-01 00:00:00'},{x:3600000,kw:10,ts:'2026-10-01 01:00:00'},{x:10800000,kw:30,ts:'2026-10-02 00:00:00'}];
 const r=c.sampling(p);assert.equal(r.median,10);assert.equal(r.medianGap,5400000);assert.equal(r.maxGap,7200000);assert.equal(r.days,2);assert.equal(r.peak.ts,p[2].ts);
 assert.equal(c.sampling([]).median,null);assert.equal(c.sampling([p[0]]).medianGap,null);
});
test('comparison intervals retain hours and minutes instead of dropping partial hours',()=>{
 assert.equal(c.duration(20700000,true),'5 h 45 min');assert.equal(c.duration(90000,true),'about 2 min');
});
