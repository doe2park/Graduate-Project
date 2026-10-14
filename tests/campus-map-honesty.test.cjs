// Pure-function tests for the data-honesty helpers in grimes-campus-map-arcgis.html.
// No browser needed: extracts the /* MAP DATA HELPERS */ block and runs it in a vm sandbox.
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('fs'),vm=require('vm'),path=require('path');
const file=process.env.CAMPUS_MAP||path.join(__dirname,'../grimes-campus-map-arcgis.html');
const source=fs.readFileSync(file,'utf8');
function block(start,end){const a=source.indexOf(start);if(a<0)return '';const b=source.indexOf(end,a);return b<0?'':source.slice(a,b)}
function load(){const ctx={console,Date,Number,Math,Intl,String,Object,Array,isFinite,isNaN,parseInt,parseFloat};vm.createContext(ctx);vm.runInContext(block('/* MAP DATA HELPERS */','/* END MAP DATA HELPERS */'),ctx);return ctx}
const T=s=>Date.parse(s); // helper for UTC instants
// 2026-09-07 12:00 PDT == 19:00Z
const NOON_PT=T('2026-09-07T19:00:00Z');

test('helper block exists',()=>{assert.ok(block('/* MAP DATA HELPERS */','/* END MAP DATA HELPERS */').length>100)});

test('escHtml escapes markup and quotes',()=>{const c=load();assert.equal(c.escHtml('<img src=x onerror="a">&\''),'&lt;img src=x onerror=&quot;a&quot;&gt;&amp;&#39;');assert.equal(c.escHtml(null),'')});

test('BMO naive timestamp is Pacific wall time; ambiguous DST is unknown',()=>{const c=load();
  assert.equal(c.bmoTimestamp('2026-09-07 12:00:00'),NOON_PT);
  assert.equal(c.bmoTimestamp('2026-01-07 12:00:00'),T('2026-01-07T20:00:00Z'));
  assert.ok(Number.isNaN(c.bmoTimestamp('2026-11-01 01:30:00')));
  assert.equal(c.bmoTimestamp('2026-09-07T19:00:00Z'),NOON_PT);
  assert.ok(Number.isNaN(c.bmoTimestamp(null)))});

test('Pacific parts: hour/day-of-week/clock are Pacific, never browser-local',()=>{const c=load();
  const p=c.ptParts(NOON_PT); // Monday 2026-09-07
  assert.equal(p.hour,12);assert.equal(p.dow,0);assert.equal(p.hhmm,'12:00');assert.equal(p.day,'2026-09-07');
  const q=c.ptParts(T('2026-09-08T06:30:00Z')); // Mon 23:30 PDT
  assert.equal(q.hour,23);assert.equal(q.dow,0);assert.equal(q.hhmm,'23:30')});

test('ageText',()=>{const c=load();assert.equal(c.ageText(5*60000),'5 min ago');assert.equal(c.ageText(30000),'just now');assert.equal(c.ageText(3*3600000+20*60000),'3h ago');assert.equal(c.ageText(50*3600000),'2d ago')});

test('reading <=45 min old is LIVE',()=>{const c=load();
  const s=c.readingState(37.3,'2026-09-07 11:30:00',NOON_PT);
  assert.equal(s.state,'live');assert.equal(s.badge,'LIVE');assert.equal(s.kw,37.3);
  assert.equal(c.readingState(1,'2026-09-07 11:15:00',NOON_PT).state,'live'); // exactly 45 min
  assert.equal(c.readingState(1,'2026-09-07 11:14:00',NOON_PT).state,'latest')});

test('older reading is neutral LATEST with Pacific clock and age, no error wording',()=>{const c=load();
  const s=c.readingState(37.3,'2026-09-07 08:05:00',NOON_PT);
  assert.equal(s.state,'latest');assert.equal(s.text,'LATEST · 08:05 · 3h ago');assert.equal(s.kw,37.3);
  assert.doesNotMatch(JSON.stringify(s),/ERROR|FAIL|OFFLINE|red/i)});

test('missing / non-finite readings are never zero and never LIVE',()=>{const c=load();
  for(const kw of [null,undefined,NaN,'12',Infinity]){const s=c.readingState(kw,'2026-09-07 11:55:00',NOON_PT);
    assert.equal(s.state,'missing');assert.equal(s.kw,null);assert.equal(s.value,'—');assert.equal(s.text,'No reading in this window')}});

test('true zero is a valid LIVE reading',()=>{const c=load();const s=c.readingState(0,'2026-09-07 11:55:00',NOON_PT);assert.equal(s.state,'live');assert.equal(s.kw,0);assert.equal(s.value,'0.0')});

test('unparseable / future / ambiguous timestamp is not LIVE',()=>{const c=load();
  for(const ts of [null,'garbage','2026-09-07 13:00:00','2026-11-01 01:30:00']){const s=c.readingState(5,ts,NOON_PT);
    assert.equal(s.state,'unknown');assert.notEqual(s.badge,'LIVE');assert.match(s.text,/time unknown/i);assert.equal(s.kw,5)}});

test('timedSeries sorts by real timestamp, drops bad rows, dedupes, ignores index spacing',()=>{const c=load();
  const pts=c.timedSeries([{ts:'2026-09-07 08:00:00',kw:3},{ts:'2026-09-07 04:00:00',kw:2},{ts:null,kw:9},{ts:'2026-09-07 08:00:00',kw:3},{ts:'2026-09-07 11:30:00',kw:null},{ts:'2026-09-07 11:45:00',kw:5}],NOON_PT);
  assert.deepEqual(Array.from(pts,p=>p.kw),[2,3,5]);
  assert.equal(pts[1].x-pts[0].x,4*3600000);
  assert.deepEqual(Array.from(c.timedSeries(undefined,NOON_PT)),[])});

test('window label comes from the covered span, not a 15-minute assumption',()=>{const c=load();
  const pts=c.timedSeries([{ts:'2026-09-07 00:00:00',kw:1},{ts:'2026-09-07 05:00:00',kw:1},{ts:'2026-09-07 11:50:00',kw:1}],NOON_PT);
  assert.equal(c.spanLabel(pts),'last 11.8 h');
  const few=c.timedSeries([{ts:'2026-09-07 11:00:00',kw:1},{ts:'2026-09-07 11:30:00',kw:1}],NOON_PT);
  assert.equal(c.spanLabel(few),'last 30 min');
  assert.equal(c.spanLabel([]),null);
  const days=c.timedSeries([{ts:'2026-09-04 12:00:00',kw:1},{ts:'2026-09-07 11:00:00',kw:1}],NOON_PT);
  assert.equal(c.spanLabel(days),'last 3 d')});

test('durText renders real offsets without assuming cadence',()=>{const c=load();assert.equal(c.durText(0),'0 m');assert.equal(c.durText(45*60000),'45 m');assert.equal(c.durText(4*3600000),'4 h');assert.equal(c.durText(6.5*3600000),'6.5 h');assert.equal(c.durText(30*3600000),'30 h');assert.equal(c.durText(60*3600000),'2.5 d')});

test('series stats are over the actual points',()=>{const c=load();const s=c.seriesStats([{kw:2},{kw:4}]);assert.equal(s.avg,3);assert.equal(s.sigma,1);assert.equal(s.peak,4);assert.equal(c.seriesStats([]),null)});

test('forecast only with a real ~15-min cadence and a fresh last reading',()=>{const c=load();
  const mk=l=>c.timedSeries(l.map(([ts,kw])=>({ts,kw})),NOON_PT);
  const fine=mk([['2026-09-07 10:45:00',1],['2026-09-07 11:00:00',2],['2026-09-07 11:15:00',3],['2026-09-07 11:30:00',4],['2026-09-07 11:45:00',5]]);
  assert.equal(c.forecastStepMs(fine,NOON_PT),15*60000);
  const sparse=mk([['2026-09-07 00:00:00',1],['2026-09-07 04:00:00',2],['2026-09-07 08:00:00',3],['2026-09-07 11:45:00',5]]);
  assert.equal(c.forecastStepMs(sparse,NOON_PT),null);
  assert.equal(c.forecastStepMs(fine,T('2026-09-07T23:00:00Z')),null); // last reading hours old
  assert.equal(c.forecastStepMs(fine.slice(-2),NOON_PT),null)});

test('meter topology marks every contributing meter and uses bmo_fetch names',()=>{const c=load();
  assert.deepEqual(Array.from(c.meterIdList('3+76+77')),['3','76','77']);
  assert.deepEqual(Array.from(c.meterIdList(null)),[]);
  const rows=c.meterTopology('3+76+77',['3','76','77']);
  assert.equal(rows.length,3);assert.ok(rows.every(r=>r.active));
  const r3=rows.find(r=>r.id==='3');assert.match(r3.label,/Roof Electric/);assert.match(r3.label,/480V/);assert.doesNotMatch(r3.label,/208V main service tie/);
  const partial=c.meterTopology('76',['3','76','77']);
  assert.deepEqual(Array.from(partial,r=>r.active),[false,true,false])});

test('household equivalent uses one named rough constant',()=>{const c=load();assert.equal(c.HOME_KW,1.25);assert.equal(c.homesEquivalent(125),100);assert.equal(c.homesEquivalent(0.1),1);assert.equal(c.homesEquivalent(null),null)});

test('daily projection text is an honest scenario, not "so far"',()=>{const c=load();const t=c.dailyAtCurrentText(100);assert.match(t,/At current demand, 24 h ≈ 2,400 kWh/);assert.doesNotMatch(t,/so far/i);assert.equal(c.dailyAtCurrentText(null),null)});

// ---- campus mood ----
function hist(){ // two buildings, hourly Pacific samples on three Mondays at 12:xx
  const h={a:[],b:[]};
  for(const d of ['2026-08-10','2026-08-17','2026-08-24','2026-08-31']){
    h.a.push({ts:d+' 12:00:00',kw:10});h.b.push({ts:d+' 12:00:12',kw:30}); // building timestamps differ by seconds
    h.a.push({ts:d+' 03:00:00',kw:1});h.b.push({ts:d+' 03:00:09',kw:1});
  }
  return h}
test('mood buckets by Pacific hour and building, not by exact ts string',()=>{const c=load();
  const cur={a:{kw:20,timestamp:'2026-09-07 12:00:00'},b:{kw:60,timestamp:'2026-09-07 12:00:20'}};
  const m=c.moodCompare(hist(),cur,NOON_PT);
  assert.equal(m.n,4);assert.equal(m.typical,40);assert.equal(m.current,80);assert.equal(m.buildings,2);assert.equal(Math.round(m.pct),100);
  assert.equal(m.hour,12);assert.equal(m.dow,0)});
test('mood compares only buildings present in both history and current',()=>{const c=load();
  const cur={a:{kw:20,timestamp:'2026-09-07 12:00:00'},b:{kw:60,timestamp:'2026-09-07 12:00:20'},c:{kw:500,timestamp:'2026-09-07 12:00:00'}};
  const m=c.moodCompare(hist(),cur,NOON_PT);assert.equal(m.current,80);assert.equal(m.buildings,2);
  const cur2={a:{kw:20,timestamp:'2026-09-07 12:00:00'}}; // b missing now: typical must exclude b too
  const m2=c.moodCompare(hist(),cur2,NOON_PT);assert.equal(m2.typical,10);assert.equal(m2.current,20)});
test('mood is hour-of-day AND day-of-week matched in Pacific time, ignoring the current hour',()=>{const c=load();
  const h=hist();h.a.push({ts:'2026-08-18 12:00:00',kw:999}); // a Tuesday
  h.a.push({ts:'2026-09-07 12:00:00',kw:20});h.b.push({ts:'2026-09-07 12:00:05',kw:60}); // current bucket
  const cur={a:{kw:20,timestamp:'2026-09-07 12:00:00'},b:{kw:60,timestamp:'2026-09-07 12:00:05'}};
  const m=c.moodCompare(h,cur,NOON_PT);assert.equal(m.n,4);assert.equal(m.typical,40)});
test('mood returns null when baseline is too thin',()=>{const c=load();
  assert.equal(c.moodCompare({a:[{ts:'2026-08-17 12:00:00',kw:1}]},{a:{kw:1,timestamp:'2026-09-07 12:00:00'}},NOON_PT),null);
  assert.equal(c.moodCompare(null,{},NOON_PT),null)});
test('mood skips buckets that do not cover every compared building',()=>{const c=load();
  const h=hist();h.b=h.b.filter(p=>!p.ts.startsWith('2026-08-17')); // b missing in one bucket
  const cur={a:{kw:20,timestamp:'2026-09-07 12:00:00'},b:{kw:60,timestamp:'2026-09-07 12:00:00'}};
  const m=c.moodCompare(h,cur,NOON_PT);assert.equal(m.n,3);assert.equal(m.typical,40)});

// ---- baseline key ----
test('baseline lookup key uses Pacific weekday/hour',()=>{const c=load();const k=c.baselineKey(T('2026-09-08T06:30:00Z'));assert.equal(k.wdayMon0,0);assert.equal(k.hr,23)});

// ---- structural regressions in the page itself ----
test('no hard-coded Grimes kW and no static fallback to roster kW',()=>{
  assert.doesNotMatch(source,/nrg:1,\s*kw:\s*37\.3/);
  assert.doesNotMatch(source,/\(b\.kw\|\|null\)/);
  assert.doesNotMatch(source,/:\(typeof b\.kw==='number' && b\.kw>0 \? b\.kw : null\)/)});
test('no UTC mislabel of BMO Pacific timestamps or 15-minute index assumptions',()=>{
  assert.doesNotMatch(source,/liveTs\.slice\(11,16\)\+' UTC'/);
  assert.doesNotMatch(source,/i\*15\*60\*1000/);
  assert.doesNotMatch(source,/stepsFromNow\*15\*60000/);
  assert.doesNotMatch(source,/σ 6hr/);
  assert.doesNotMatch(source,/24-hour average/);
  assert.doesNotMatch(source,/15m cadence/)});
test('stanley is not presented as a metered-offline building',()=>{assert.doesNotMatch(source,/id:'stanley'[^\n]*nrg:1/)});
test('user chat text is not injected as HTML',()=>{assert.match(source,/if\(type==='user'\)d\.textContent=t;else d\.innerHTML=t/)});
test('clickable chips and cards are keyboard-operable',()=>{assert.doesNotMatch(source,/<div class="chat-q" onclick/);assert.match(source,/<button[^>]*class="chat-q"/);assert.match(source,/card\.setAttribute\('role','button'\)/);assert.match(source,/card\.tabIndex=0/)});
test('map polls the feed at most every 5 minutes',()=>{assert.match(source,/setInterval\(fetchLiveData,\s*300000\)/);assert.doesNotMatch(source,/setInterval\(fetchLiveData,\s*60000\)/)});
test('fetchLiveData resets per-building live fields every fetch',()=>{const a=source.indexOf('async function fetchLiveData');const body=source.slice(a,source.indexOf('// Update stats',a));assert.match(body,/b\.kw\s*=\s*null/);assert.match(body,/b\.sparkline\s*=\s*\[\]/)});
test('static roster carries no kW values',()=>{const a=source.indexOf('const D=[');const roster=source.slice(a,source.indexOf('];',a));assert.doesNotMatch(roster,/[,{ ]kw:\s*\d/)});
