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
test('stale, future and missing readings never receive a recent badge',()=>{
 assert.equal(typeof c.freshness,'function');const now=Date.parse('2026-10-13T02:00:00Z');
 assert.equal(c.freshness({kw:0,timestamp:'2026-10-12 18:45:00'},now).label,'Recent');
 assert.equal(c.freshness({kw:10,timestamp:'2026-10-11 18:45:00'},now).label,'Stale');
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
