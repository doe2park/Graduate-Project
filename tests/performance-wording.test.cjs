// Wording honesty checks for grimes-performance.html (no browser needed).
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('fs'),path=require('path');
const source=fs.readFileSync(process.env.PERF||path.join(__dirname,'../grimes-performance.html'),'utf8');
test('no unevidenced "revenue-grade" claim',()=>{assert.doesNotMatch(source,/revenue-grade/i);assert.match(source,/utility meter counters/)});
test('no "recomputed every 15 minutes" cadence claim (scheduler fires every few hours)',()=>{assert.doesNotMatch(source,/recomputed (from the meter archive )?every 15 minutes/i);assert.doesNotMatch(source,/next 15-minute run/i);assert.match(source,/Recomputed when new meter data arrives/)});
