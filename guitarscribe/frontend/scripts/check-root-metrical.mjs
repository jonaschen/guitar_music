// Production read-only preview, then a browser-only view of the proposed v2 document.
// Never applies a plan or writes an adoption to the real service.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:5273',job='83a3643ab3814172a046cebf709f3413';
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const out=new URL('../../output/evaluation/root-practice-metrical-2026-11-12/',import.meta.url);await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
  const context=await browser.newContext({httpCredentials:{...credentials,send:'always'},viewport:{width:1440,height:1000}});
  await context.route(base+'/**',route=>route.continue({headers:{...route.request().headers(),authorization:'Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64')}}));
  const prefix=base+'/backend/api/v1/jobs/'+job;
  const get=async url=>{const r=await context.request.get(url);if(!r.ok())throw Error('GET '+r.status());return r.json();};
  const before=await get(prefix),sheet=await get(prefix+'/root-practice');
  const response=await context.request.post(prefix+'/root-practice/segment-plan',{data:{document:sheet.document,grid:{bpm:115,beats:4,anchor:15.959}}});
  if(!response.ok())throw Error('Plan '+response.status());const plan=await response.json();
  const page=await context.newPage(),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(['PUT','DELETE'].includes(r.method()))writes.push(r.method()+' '+new URL(r.url()).pathname);});
  await page.goto(base+'/root-practice-2026-11-12/?practice=roots&job='+job);await page.getByLabel('小節對齊點秒數').waitFor();
  await page.getByLabel('小節對齊點秒數').fill('15.959');await page.getByRole('button',{name:'預覽小節分段',exact:true}).click();await page.getByRole('region',{name:'分段預覽',exact:true}).waitFor();
  await page.getByRole('region',{name:'分段預覽',exact:true}).screenshot({path:new URL('production-preview.png',out).pathname});
  // Mock only the practice GET for the second stage. The production root document is untouched.
  await page.route(prefix+'/root-practice',route=>route.request().method()==='GET'?route.fulfill({json:{...sheet,document:plan.document}}):route.abort());
  await page.reload();await page.getByRole('region',{name:'目前小節細分'}).waitFor();
  const count=await page.locator('.root-progression button').count();if(count!==plan.document.segments.length)throw Error('Incorrect segment navigation');
  const special=plan.document.segments.findIndex(s=>s.start>0&&s.end-s.start<240/115-.001);
  await page.locator('.root-progression button').nth(special>=0?special:0).click();
  if(!/小節/.test(await page.locator('.root-segment-heading h2').innerText()))throw Error('No metrical unit label');
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:900});if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Overflow '+width);
    await page.locator('.root-progression').screenshot({path:new URL(`metrical-nav-${width}.png`,out).pathname});
    await page.getByRole('region',{name:'當段聽辨'}).screenshot({path:new URL(`metrical-listen-${width}.png`,out).pathname});
  }
  await page.getByLabel('聽一點前後文',{exact:true}).uncheck();await page.getByRole('button',{name:'播放這段',exact:true}).click();await page.getByRole('button',{name:'暫停',exact:true}).waitFor({timeout:45000});await page.waitForTimeout(900);await page.getByRole('button',{name:'暫停',exact:true}).click();
  const after=await get(prefix),saved=await get(prefix+'/root-practice');if(JSON.stringify(after.score)!==JSON.stringify(before.score)||JSON.stringify(saved)!==JSON.stringify(sheet))throw Error('User data changed during read-only check');
  if(errors.length||writes.length)throw Error('Unexpected page error or mutation');
  const result={job,old_segments:sheet.document.segments.length,proposed_segments:count,bars:plan.bars,exception_bars:plan.exceptions.length,review_segments:plan.review.length,preview_from_real_api:true,applied_view_in_browser_only:true,real_audio_played:true,widths:[320,390,768,1440],page_errors:errors,writes,score_and_practice_unchanged:true};
  await fs.writeFile(new URL('production.json',out),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
