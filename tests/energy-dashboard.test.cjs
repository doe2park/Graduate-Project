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
test('availability partitions buildings, not meters, and includes separate channels without summing',()=>{
 const r=c.availability({a:{kw:0},b:{kw:null},c:{kw:null,electricity_channels:[{kw:10},{kw:null}]}});
 assert.equal(r.available,2);assert.equal(r.missing,1);assert.equal(r.total,3);
});
test('meter coverage counts IDs with an explicit configured denominator',()=>{
 assert.equal(c.meterCoverage({meter:'3+76+77',meters_configured:['3','76','77']}).label,'3 of 3 configured device IDs returned kW');
 assert.equal(c.meterCoverage({meter:null,meters_configured:['3','76','77']}).count,0);
 assert.equal(c.meterCoverage({meter:'76'}).expected,null);
});
test('Soda channel-only readings do not contradict the brief or inventory availability',()=>{
 const elements={};const element=id=>elements[id]??=({innerHTML:'',textContent:'',value:'',href:'https://example.test/source',addEventListener(){},insertAdjacentHTML(_,v){this.innerHTML+=v}});
 const ui=html.match(/<script>\nconst DATA_URL[\s\S]*?<\/script>/)[0].replace(/^<script>/,'').replace(/<\/script>$/,'').replace('load();setInterval(load,60000);','');
 const ctx={Intl,Date,document:{getElementById:element,querySelectorAll:()=>[]}};vm.createContext(ctx);vm.runInContext(source+ui,ctx);
 vm.runInContext("selected='soda';data={buildings:{soda:{name:'Soda Hall',kw:null,meter:null,meters_configured:['3','76','77'],electricity_channels:[{kw:0,column:'Main 1',status:'observed',timestamp:'2026-10-12 18:45:00'},{kw:42.5,column:'Main 2',status:'observed',timestamp:'2026-10-12 18:45:00'}]}}};renderCampus();render();",ctx);
 assert.match(element('reading-brief').innerHTML,/Individual channels/);assert.match(element('reading-brief').innerHTML,/Device #250/);assert.doesNotMatch(element('reading-brief').innerHTML,/0 of 3 configured/);
 assert.doesNotMatch(element('reading-brief').innerHTML,/No electricity reading is available/);
 assert.match(element('inventory-summary').textContent,/1 with aggregate or separate channel readings · 0 without/);
 assert.match(element('inventory').innerHTML,/Device #250: 2 of 2/);
 assert.match(element('reading-brief').innerHTML,/0 kW/);
});
test('demand bands form a true partition including zero and boundary values',()=>{
 const r=c.demandBands([0,50,99.9,100,200].map(kw=>({kw})));
 assert.equal(r.reduce((n,b)=>n+b.count,0),5);assert.equal(r[0].count,1);assert.equal(r[1].count,2);assert.equal(r[2].count,1);assert.equal(r[3].count,1);
 assert.equal(c.demandBands([]).reduce((n,b)=>n+b.count,0),0);
});
test('daily summaries use Pacific observation dates and retain actual extrema and timestamps',()=>{
 const p=c.series([{kw:0,ts:'2026-10-01 23:45:00'},{kw:20,ts:'2026-10-02 00:15:00'},{kw:40,ts:'2026-10-02 12:15:00'}]);
 const r=c.dailySummary(p);assert.equal(r.length,2);assert.equal(r[1].median,30);assert.equal(r[1].min.kw,20);assert.equal(r[1].max.ts,'2026-10-02 12:15:00');assert.equal(r[1].count,2);
});
test('short trend breaks gaps above an hour and never bridges absent observations',()=>{
 const r=c.connectedSamples([{x:0,kw:0},{x:900000,kw:10},{x:7200000,kw:50}]);
 assert.equal(r.length,4);assert.equal(r[2].y,null);assert.equal(r[3].y,50);
});
test('archive observations use BMO timestamp and preserve per-row source in CSV',()=>{
 const r=c.archivePoints({buildings:{g:{kw:0,timestamp:'2026-10-02 23:00:00'},s:{kw:null}}},'https://example.test/archive/2026-10-03.json');
 assert.equal(r.g[0].ts,'2026-10-02 23:00:00');assert.equal(r.s.length,0);
 assert.match(c.exportCSV('g',{name:'G'},c.series(r.g)),/archive\/2026-10-03.json/);
});
test('today uses the actual current Pacific calendar date, not the last recorded day',()=>{
 const p=c.series([{kw:10,ts:'2026-10-12 23:30:00'}]);
 assert.equal(c.todayPoints(p,Date.parse('2026-10-13T06:45:00Z')).length,1);
 assert.equal(c.todayPoints(p,Date.parse('2026-10-13T08:00:00Z')).length,0);
});
test('weekly summaries group Pacific calendar weeks and preserve the actual extrema',()=>{
 const p=c.series([{kw:10,ts:'2026-10-04 23:30:00'},{kw:30,ts:'2026-10-05 00:30:00'},{kw:50,ts:'2026-10-07 04:00:00'}]);
 const r=c.weeklySummary(p);assert.equal(r.length,2);assert.equal(r[1].day,'Week of 2026-10-05');assert.equal(r[1].median,40);assert.equal(r[1].max.ts,'2026-10-07 04:00:00');
});
test('archive comparisons isolate the current responding meter set',()=>{
 const rows=[{meter:'3',kw:30},{meter:'77+3+76',kw:100},{kw:80}];
 const result=c.compatibleArchive(rows,{meter:'3+76+77'});assert.equal(result.length,2);assert.equal(result[0].kw,100);
});
test('latest-day fallback excludes future observations',()=>{
 const now=Date.parse('2026-10-13T12:00:00Z'),p=c.series([{kw:10,ts:'2026-10-12 23:00:00'},{kw:99,ts:'2026-10-14 01:00:00'}]);
 const r=c.dayOverview(p,now);assert.equal(r.label,'2026-10-12');assert.equal(r.points[0].kw,10);assert.equal(r.isToday,false);
});
test('archive deduplication has deterministic newest-file priority regardless of request completion',()=>{
 const cache=new Map([['2026-10-13',{g:[{kw:20,ts:'2026-10-12 20:00:00',source:'new'}]}],['2026-10-12',{g:[{kw:10,ts:'2026-10-12 20:00:00',source:'old'}]}]]);
 const rows=c.series(c.mergeArchives(cache).g);assert.equal(rows.length,1);assert.equal(rows[0].kw,20);assert.equal(rows[0].source,'new');
});
test('dark restoration uses original compact shell without overwriting saved checkpoints',()=>{
 assert.match(html,/<header class="hdr">/);
 assert.match(html,/<main class="wrap">/);
 assert.match(html,/--bg:#0a1020/);
 assert.match(html,/<details class="research-details"/);
 for(const [file,hash] of [['energy-dashboard-before-97c9751.html','cb8a882503f7863ec0fd6a5a981f996dfc0a50b3c804c8a524ea887f94cb0150'],['energy-dashboard-current-ba3d03c7.html','89ee28f2c45a1a96d4a1a90055678ec5dbef567f20b9afb6daf4f59b178f8479']])assert.equal(require('node:crypto').createHash('sha256').update(fs.readFileSync(file)).digest('hex'),hash);
});
test('dark overview leads with selected observed demand and retains honest trend gaps',()=>{
 const elements={};const element=id=>elements[id]??=({innerHTML:'',textContent:'',value:'',href:'https://example.test/source',addEventListener(){},insertAdjacentHTML(_,v){this.innerHTML+=v}}),configs={};
 const ui=html.match(/<script>\nconst DATA_URL[\s\S]*?<\/script>/)[0].replace(/^<script>/,'').replace(/<\/script>$/,'').replace('load();setInterval(load,60000);','');
 function FakeChart(el,config){configs[Object.keys(elements).find(k=>elements[k]===el)]=config;this.destroy=()=>{}}FakeChart.defaults={font:{}};FakeChart.register=()=>{};
 const ctx={Intl,Date,Chart:FakeChart,document:{getElementById:element,querySelectorAll:()=>[]}};vm.createContext(ctx);vm.runInContext(source+ui,ctx);
 vm.runInContext("hours=0;selected='grimes';data={buildings:{grimes:{name:'Grimes Engineering Center',kw:116.8,timestamp:'2026-10-12 20:15:01',meter:'3+76+77'}}};hist={grimes:[{kw:0,ts:'2026-10-12 01:00:00'},{kw:116.8,ts:'2026-10-12 20:15:01'}]};render();",ctx);
 assert.match(element('stats').innerHTML,/Latest demand/);assert.match(element('stats').innerHTML,/116.8/);assert.doesNotMatch(element('stats').innerHTML,/Daily Energy|Campus Load|Daily Cost/);
 assert.match(element('reading-brief').innerHTML,/2026-10-12 20:15:01 Pacific/);assert.match(element('reading-brief').innerHTML,/3, 76, 77/);
 assert.equal(configs.trend.data.datasets[0].borderColor,'#FDB515');
 assert.equal(c.connectedSamples(c.series([{kw:0,ts:'2026-10-12 01:00:00'},{kw:2,ts:'2026-10-12 04:00:00'}]))[1].y,null);
});
test('24-hour guide lines adapt to retained observation spacing but cap long gaps at six hours',()=>{
 const h=3600000,p=[0,9.375,15.125,16.625].map((x,i)=>({x:x*h,kw:i,ts:String(i)}));
 assert.equal(typeof c.connectionLimit,'function');const limit=c.connectionLimit(p);assert.equal(limit,6*h);
 const line=c.connectedSamples(p,limit);assert.equal(line.filter(p=>p.y===null).length,1);assert.equal(line[0].y,0);assert.equal(line.at(-1).y,3);
 assert.equal(c.connectionLimit([{x:0},{x:h/4},{x:h/2}]),h);assert.equal(c.connectionLimit([]),h);
 assert.equal(c.connectedSamples([{x:0,kw:1},{x:6*h+1,kw:2}],6*h)[1].y,null);
});
