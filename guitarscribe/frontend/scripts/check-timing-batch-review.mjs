// Check an invited deployment without modifying any existing work or credentials.
// Usage: node scripts/check-timing-batch-review.mjs BASE_URL REVIEW_DIR ACCESS_FILE
import {chromium,request} from '@playwright/test';
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
const [base,directory,accessFile]=process.argv.slice(2);
const credentials=JSON.parse(await readFile(accessFile,'utf8'));
const anonymous=await request.newContext({extraHTTPHeaders:{'ngrok-skip-browser-warning':'1'}});
assert.equal((await anonymous.get(base+'/timing-batch-review-2026-11-04/')).status(),401);
await anonymous.dispose();
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const result={review:[],candidates:[],errors:[]};
try{
 const context=await browser.newContext({httpCredentials:credentials,extraHTTPHeaders:{'ngrok-skip-browser-warning':'1'},viewport:{width:390,height:844}});
 const page=await context.newPage();page.on('pageerror',e=>result.errors.push(String(e)));
 await page.goto(base+'/timing-batch-review-2026-11-04/',{waitUntil:'networkidle',timeout:60000});
 await page.locator('section').nth(2).waitFor();
 const rows=JSON.parse(await readFile(path.join(directory,'packet.json'),'utf8'));
 for(const row of rows){
  const section=page.locator(`section[data-number="${row.number}"]`);const audio=section.locator('audio');
  await audio.evaluate(async a=>{await a.play()});await page.waitForTimeout(1000);
  const playing=await audio.evaluate(a=>({time:a.currentTime,duration:a.duration,paused:a.paused,error:a.error?.message}));
  assert(!playing.paused && playing.time>.3 && Math.abs(playing.duration-40)<.01 && !playing.error);
  await audio.evaluate(a=>{a.currentTime=20});await section.getByRole('button',{name:'A',exact:true}).click();
  await page.waitForFunction(n=>{const a=document.querySelector(`section[data-number="${n}"] audio`);return a && !a.paused && a.readyState>=3 && a.currentTime>20.05},row.number,{timeout:30000});
  await audio.evaluate(a=>a.pause());
  for(const width of [320,390,1440]){await page.setViewportSize({width,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
  result.review.push({number:row.number,plays:true,switch_keeps_position:true,responsive:true});
 }
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:path.join(directory,'review-mobile.png'),fullPage:true});
 await page.locator('select').first().selectOption('能跟拍');await page.getByRole('button',{name:'複製回報'}).click();
 assert((await page.getByLabel('可複製的回報').inputValue()).includes('1 跟拍：能跟拍'));
 await page.reload({waitUntil:'networkidle'});assert.equal(await page.locator('select').first().inputValue(),'能跟拍');
 for(const row of rows.filter(r=>r.revision)){
  await page.goto(base+'/?revision='+row.revision,{waitUntil:'networkidle',timeout:60000});
  await page.getByLabel('和弦譜',{exact:true}).waitFor();
  assert.equal(await page.getByRole('note').filter({hasText:'拍格試驗稿'}).count(),1);
  assert(await page.getByRole('button',{name:'播放',exact:true}).isEnabled());
  await page.getByRole('button',{name:'播放',exact:true}).click();
  await page.waitForTimeout(2500);await page.getByRole('button',{name:'暫停',exact:true}).waitFor();
  assert((await page.locator('.playback-status').innerText()).includes('播放中'));
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  for(const width of [320,390,1440]){await page.setViewportSize({width,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
  result.candidates.push({revision:row.revision,grid:true,source_mix_plays:true,responsive:true});
 }
 // Exercise autosave on a fresh test copy; public candidates remain immutable.
 const original=await (await context.request.get(base+'/backend/revisions/'+rows[0].revision)).json();
 const created=await context.request.post(base+'/backend/revisions',{data:{score:original,create_new:true}});assert(created.ok());
 const testId=(await created.json()).revision_id;
 await page.goto(base+'/?revision='+testId,{waitUntil:'networkidle'});
 await page.getByText('練習與編輯',{exact:true}).click();
 const save=()=>page.waitForResponse(r=>r.url().endsWith('/backend/revisions') && r.request().method()==='POST' && r.ok());
 let pending=save();await page.getByRole('button',{name:'每拍一下',exact:true}).click();let response=await pending;
 let body=response.request().postDataJSON();assert.equal(body.score.rhythm.pattern_id,'observed-quarter-beats-v1');assert.deepEqual(body.score.chords,original.chords);assert.deepEqual(body.score.beats,original.beats);
 pending=save();await page.getByRole('button',{name:'復原',exact:true}).click();response=await pending;assert.equal(response.request().postDataJSON().score.rhythm.pattern_id,original.rhythm.pattern_id);
 pending=save();await page.getByRole('button',{name:'重做',exact:true}).click();response=await pending;assert.equal(response.request().postDataJSON().score.rhythm.pattern_id,'observed-quarter-beats-v1');
 await page.reload({waitUntil:'networkidle'});await page.getByText('練習與編輯',{exact:true}).click();assert(await page.getByRole('button',{name:'已選：每拍一下',exact:true}).isDisabled());
 assert.deepEqual(await (await context.request.get(base+'/backend/revisions/'+rows[0].revision)).json(),original);
 result.fresh_copy_save_undo_redo_reload=true;result.original_candidate_unchanged=true;
 assert.deepEqual(result.errors,[]);
 await writeFile(path.join(directory,'deployed-browser-checks.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result));
}finally{await browser.close();}
