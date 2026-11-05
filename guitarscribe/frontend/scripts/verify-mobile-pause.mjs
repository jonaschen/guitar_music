import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const out=new URL('../../output/evaluation/reading-candidate-2026-11-05/',import.meta.url);
const credentials=JSON.parse(await readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const base='http://127.0.0.1:4181',job='1b4158f1acee4beaa9af7cb42f3f52a0';
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true}),results=[];
let currentPage,currentCase,currentCompiled;const responses=[];
try{
  for(const width of [320,390])for(const view of ['auto','timeline']){
    const context=await browser.newContext({httpCredentials:credentials,viewport:{width,height:844}}),page=await context.newPage();
    currentPage=page;currentCase={width,view};
    page.on('response',r=>{const path=new URL(r.url()).pathname;if(path.includes('/api/v1/jobs/')||path.endsWith('/manifest'))responses.push({width,view,path,status:r.status()});});
    let writes=0,compiled;const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/revisions',r=>{if(r.request().method()==='POST'){writes++;return r.abort();}return r.continue();});
    await page.route('**/scores/playback/manifest',r=>{compiled=r.request().postDataJSON();currentCompiled=compiled;return r.continue();});
    // Pre-authenticate only our local proxy; repeated fresh-context challenges
    // otherwise consume the invitation gate's failed-login budget.
    await page.route(`${base}/backend/**`,r=>r.fallback({headers:{...r.request().headers(),authorization:'Basic '+Buffer.from(`${credentials.username}:${credentials.password}`).toString('base64')}}));
    await page.goto(`${base}/?job=${job}${view==='auto'?'&timingView=auto':''}`);
    let target;
    if(view==='auto'){
      const sheet=page.getByLabel('局部小節預覽',{exact:true});await sheet.waitFor();
      target=sheet.locator('.partial-region').nth(1).locator('button').first();
    }else{
      const sheet=page.getByLabel('和弦時間表',{exact:true});await sheet.waitFor();
      target=sheet.getByRole('button',{name:/^播放 (?:4\d|[5-9]\d)\.\d+ 秒的/}).first();
    }
    // Retain original+guitar; normal user clicks only.
    await target.click();const pause=page.getByRole('button',{name:'暫停',exact:true});await pause.waitFor();
    await page.mouse.wheel(0,650);await page.waitForTimeout(300);
    const rect=await page.locator('.timeline-transport').evaluate(el=>{const r=el.getBoundingClientRect();return {top:r.top,bottom:r.bottom};});
    assert(rect.top>=0&&rect.bottom<844);
    await page.screenshot({path:new URL(`mobile-pause-${width}-${view}.png`,out).pathname});
    const started=performance.now();await pause.click({timeout:5000});const pauseClickMs=performance.now()-started;
    await page.getByRole('button',{name:'播放',exact:true}).waitFor();
    const original=JSON.parse(await readFile(new URL('new-job.json',out),'utf8')).score;
    assert.deepEqual(compiled.chords,original.chords);assert.deepEqual(compiled.beats,original.beats);
    assert.equal(writes,0);assert.deepEqual(errors,[]);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    results.push({width,view,mode:'mix',manual_wheel:650,transport:rect,pause_click_ms:pauseClickMs,writes,errors,playback_input_unchanged:true});
    console.log(JSON.stringify(results.at(-1)));
    await context.close();
  }
  await writeFile(new URL('mobile-pause-results.json',out),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}catch(error){
  if(currentPage&&!currentPage.isClosed())await currentPage.screenshot({path:new URL('mobile-pause-failure.png',out).pathname});
  await writeFile(new URL('mobile-pause-failure.json',out),JSON.stringify({case:currentCase,error:error.message,responses,completed:results,compiled:!!currentCompiled,alerts:currentPage?await currentPage.locator('[role=alert]').allTextContents():[],status:currentPage?await currentPage.locator('.playback-status').allTextContents():[]},null,2));
  throw error;
}finally{await browser.close();}
