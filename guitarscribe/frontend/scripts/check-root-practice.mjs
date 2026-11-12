// Real API/audio integration. Writes are allowed only on the isolated test port.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base=process.env.ROOT_PRACTICE_URL||'http://127.0.0.1:5275';
const pagePath=process.env.ROOT_PRACTICE_PAGE_PATH||'/';
const job=process.env.ROOT_PRACTICE_JOB||'83a3643ab3814172a046cebf709f3413';
const write=process.env.ROOT_PRACTICE_TEST_WRITES==='1';
if(write&&base!=='http://127.0.0.1:5275')throw Error('Write checks require isolated port 5275');
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const out=new URL('../../output/evaluation/root-practice-2026-11-12/browser/',import.meta.url);await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const context=await browser.newContext({httpCredentials:{username:credentials.username,password:credentials.password,send:'always'},viewport:{width:1440,height:1000}});
const page=await context.newPage(),errors=[],mutations=[];
page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(['PUT','POST','DELETE'].includes(r.method()))mutations.push({method:r.method(),path:new URL(r.url()).pathname});});
const prefix=base+'/backend/api/v1/jobs/'+job;
const json=async(url)=>{const r=await context.request.get(url);if(!r.ok())throw Error('GET failed: '+url+' '+r.status());return r.json();};
const before=await json(prefix),snapshot=await json(prefix+'/root-practice');
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const sourceHash=hash(before.score);
let index=-1,rank;
for(const [i,s]of snapshot.document.segments.entries()){
  if(s.start<15||s.end-s.start<1.5||s.start>90)continue;
  const response=await context.request.post(prefix+'/root-candidates/rank',{data:{fingerprint:snapshot.document.source.fingerprint,start:s.start,end:s.end}});
  if(!response.ok())throw Error('Candidate request failed: '+response.status());
  rank=await response.json();if(rank.candidates.length===3){index=i;break;}
}
if(index<0)throw Error('No representative prepared segment');
try{
  await page.goto(base+pagePath+'?job='+job+'&practice=roots');
  await page.getByRole('main',{name:'根音抓歌練習'}).waitFor();
  await page.locator('.root-progression button').nth(index).click();
  await page.locator('.root-candidates button').nth(2).waitFor();
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:900});await page.locator('.root-clues').scrollIntoViewIfNeeded();
    await page.waitForFunction(()=>{const nav=document.querySelector('.root-progression'),selected=nav?.querySelector('[aria-current=step]');if(!nav||!selected)return false;const n=nav.getBoundingClientRect(),s=selected.getBoundingClientRect();return s.left>=n.left-1&&s.right<=n.right+1;});
    if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Horizontal overflow '+width);
    await page.screenshot({path:new URL(`real-${job}-${write?'write':'readonly'}-${width}.png`,out).pathname,fullPage:true});
  }
  await page.locator('.root-candidates button').nth(1).click();
  await page.getByRole('button',{name:'暫停',exact:true}).waitFor({timeout:45000});
  await page.waitForTimeout(1000);
  const position=await page.getByLabel('根音練習播放位置').inputValue();
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  const afterAudition=await json(prefix+'/root-practice');
  if(afterAudition.version!==snapshot.version)throw Error('Audition wrote a decision');
  if(write){
    await page.getByRole('button',{name:'採用這個根音',exact:true}).click();
    await page.getByLabel('根音保存狀態').filter({hasText:'已保存'}).waitFor();
    const saved=await json(prefix+'/root-practice');if(saved.document.segments[index].root!==rank.candidates[1].pitch_class)throw Error('Saved root mismatch');
    await page.reload();await page.locator('.root-progression button').nth(index).click();
    await page.locator('.root-current').filter({hasText:'已採用'}).waitFor();
    await page.getByRole('button',{name:'連聽我的行進'}).click();await page.getByRole('button',{name:'暫停',exact:true}).waitFor({timeout:45000});await page.getByRole('button',{name:'暫停',exact:true}).click();
  }
  const after=await json(prefix);if(hash(after.score)!==sourceHash)throw Error('Source score changed');
  if(!write&&mutations.some(r=>r.method!=='POST'||!r.path.endsWith('/root-candidates/rank')))throw Error('Unexpected production mutation');
  if(errors.length)throw Error(errors.join('\n'));
  const result={job,base,writes:write,selected_segment:index,source_score_unchanged:true,audition_did_not_save:true,playback_position:position,
    widths:[320,390,768,1440],page_errors:errors,requests:mutations};
  await fs.writeFile(new URL(`real-${job}-${write?'write':'readonly'}.json`,out),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
}finally{await browser.close();}
