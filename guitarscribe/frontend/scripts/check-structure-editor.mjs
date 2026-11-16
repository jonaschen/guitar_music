// Real recordings: read-only deployment checks; any write request is refused.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base='http://127.0.0.1:5273';
const root=new URL('../../output/evaluation/song-structure-editor-2026-11-17/',import.meta.url);
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const auth='Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64');
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const context=await browser.newContext({httpCredentials:{username:credentials.username,password:credentials.password,origin:base,send:'always'},viewport:{width:1440,height:1100}});
const writes=[],errors=[],results=[],rankRequests=[];
await context.route(base+'/**',route=>{const readRank=route.request().method()==='POST'&&new URL(route.request().url()).pathname.endsWith('/root-candidates/rank');if(readRank)rankRequests.push(new URL(route.request().url()).pathname);if(!['GET','HEAD'].includes(route.request().method())&&!readRank){writes.push(route.request().method()+' '+new URL(route.request().url()).pathname);return route.abort();}return route.continue({headers:{...route.request().headers(),authorization:auth}});});
const get=async path=>{const r=await context.request.get(base+'/backend/api/v1/jobs/'+path);if(!r.ok())throw Error('GET failed '+r.status());return r.json();};
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>{window.__tones=0;const start=OscillatorNode.prototype.start;OscillatorNode.prototype.start=function(...args){window.__tones++;return start.apply(this,args)};});
try{
 for(const job of ['83a3643ab3814172a046cebf709f3413','a3be29912a7045448765290d7cba2f6c']){
  const before=await get(job),roots=await get(job+'/root-practice'),saved=await get(job+'/song-structure');
  const doc=saved.document;if(!doc)throw Error('Missing seeded structure');
  const expectedRoot=JSON.parse(await fs.readFile(new URL(`../song-structure-2026-11-15/${job}/root-before.json`,root),'utf8'));
  const expectedScore=JSON.parse(await fs.readFile(new URL(`../song-structure-2026-11-15/${job}/score-before.json`,root),'utf8'));
  if(hash(roots)!==hash(expectedRoot)||hash(before.score)!==hash(expectedScore))throw Error('Protected pre-inference source changed');
  await page.goto(`${base}/visual-practice-2026-11-14/?practice=structure&job=${job}`,{waitUntil:'domcontentloaded'});
  await page.getByLabel('結構保存狀態').filter({hasText:'已保存'}).waitFor();
  if(await page.getByRole('navigation',{name:'歌曲段落清單'}).getByRole('button').count()!==doc.sections.length)throw Error('Incorrect section count');
  const target=doc.sections[2];await page.getByRole('button',{name:`選取第 3 段 ${target.display_label}`,exact:true}).click();
  await page.getByRole('button',{name:'聽這段',exact:true}).click();
  await page.waitForFunction(start=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>start+.1&&a.currentTime<start+4},target.start,{timeout:45000});
  const played=await page.locator('audio').evaluate(a=>{a.pause();return {time:a.currentTime,src:a.currentSrc,duration:a.duration}});
  if(!played.src.includes(doc.source.audio_sha256)||Math.abs(played.duration-doc.source.duration)>.05)throw Error('Wrong audio');
  for(const width of [320,390,768,1440]){
   await page.setViewportSize({width,height:1100});if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Overflow '+width);
   if(!await page.getByRole('navigation',{name:'歌曲段落清單'}).getByRole('button').evaluateAll(rows=>rows.every(b=>b.querySelector('small').getBoundingClientRect().bottom<=b.getBoundingClientRect().bottom)))throw Error('Section rows overlap '+width);
   await page.screenshot({path:new URL(`${job}-${width}.png`,root).pathname,fullPage:true});
  }
  if(await page.getByText('原曲暫時無法播放，請確認連線後再試。',{exact:true}).count())throw Error('Playback error banner');
  const tones=await page.evaluate(()=>window.__tones);if(tones!==0)throw Error('Unexpected synthesis');
  await page.getByRole('link',{name:'練這段根音',exact:true}).click();
  await page.waitForFunction(id=>document.querySelector('select[aria-label="歌曲大段"]')?.value===id,target.id,{timeout:45000});
  const count=await page.getByRole('navigation',{name:'根音行進'}).getByRole('button').count();
  const expected=roots.document.segments.filter(s=>s.start<target.end&&s.end>target.start).length;
  if(count!==expected||count>=roots.document.segments.length)throw Error('Root filter incorrect');
  await page.getByLabel('歌曲大段',{exact:true}).selectOption('');
  if(await page.getByRole('navigation',{name:'根音行進'}).getByRole('button').count()!==roots.document.segments.length)throw Error('Full root list not restored');
  if(hash(await get(job+'/root-practice'))!==hash(roots)||hash((await get(job)).score)!==hash(before.score)||hash(await get(job+'/song-structure'))!==hash(saved))throw Error('Read-only check mutated data');
  results.push({job,sections:doc.sections.length,root_segments:roots.document.segments.length,filtered_root_segments:count,widths:[320,390,768,1440],played_at:played.time,source_sha_checked:true,roots_unchanged:true,score_unchanged:true,structure_unchanged:true,oscillators:tones});
 }
 if(errors.length||writes.length)throw Error(JSON.stringify({errors,writes}));
 await fs.writeFile(new URL('browser.json',root),JSON.stringify({results,errors,writes,read_only_rank_requests:rankRequests.length},null,2)+'\n');console.log(JSON.stringify({results,errors,writes,read_only_rank_requests:rankRequests.length},null,2));
}finally{await browser.close()}
