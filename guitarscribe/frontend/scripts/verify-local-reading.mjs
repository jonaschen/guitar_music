import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const base=process.env.READING_CANDIDATE_URL??'http://127.0.0.1:4181';
const job='1b4158f1acee4beaa9af7cb42f3f52a0';
const out=new URL('../../output/evaluation/reading-candidate-2026-11-05/',import.meta.url);
const credentials=JSON.parse(await readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const context=await browser.newContext({httpCredentials:credentials});
const page=await context.newPage();let writes=0;const errors=[];let compiled;
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/revisions',r=>{writes++;return r.fulfill({status:409,body:'Read-only verification'});});
await page.route('**/scores/playback/manifest',async r=>{compiled=r.request().postDataJSON();return r.continue();});
const evidence=[];
try{
  await page.goto(`${base}/?job=${job}&timingView=auto`);
  const sheet=page.getByLabel('局部小節預覽',{exact:true});await sheet.waitFor();
  const sources=JSON.parse(await readFile(new URL('sources.json',out),'utf8'));
  const expected=sources.find(s=>s.job.id===job).preview.regions.reduce((n,r)=>n+r.bars.length,0);
  const bars=await sheet.locator('.notation-measure').count();assert.equal(bars,expected);
  for(const width of [320,390,1440]){
    await page.setViewportSize({width,height:900});
    await page.getByLabel('讀譜方式',{exact:true}).scrollIntoViewIfNeeded();
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:new URL(`new-job-${width}.png`,out).pathname});
    evidence.push({width,bars,overflow:false});
  }
  await page.getByRole('button',{name:'時間表',exact:true}).click();
  await page.getByLabel('和弦時間表',{exact:true}).waitFor();
  await page.getByRole('button',{name:'局部譜 · 待確認',exact:true}).click();
  await sheet.waitFor();
  await page.getByLabel('播放聲音',{exact:true}).selectOption('guitar');
  await sheet.locator('.partial-region button').first().click();
  await page.getByRole('button',{name:'暫停',exact:true}).waitFor();
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  const original=JSON.parse(await readFile(new URL('new-job.json',out),'utf8')).score;
  assert.deepEqual(compiled.chords,original.chords);assert.deepEqual(compiled.beats,original.beats);
  assert.equal(writes,0);assert.deepEqual(errors,[]);
  await writeFile(new URL('browser-real.json',out),JSON.stringify({job,evidence,revision_write_attempts:writes,page_errors:errors,playback_input_unchanged:true},null,2));
  console.log(JSON.stringify({job,bars,viewports:evidence.length,writes,page_errors:errors.length,playback_input_unchanged:true}));
}finally{await browser.close();}
