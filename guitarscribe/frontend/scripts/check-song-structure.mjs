// Read-only browser validation against the two real, authenticated local recordings.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base='http://127.0.0.1:5273';
const root=new URL('../../output/evaluation/song-structure-2026-11-15/',import.meta.url);
const protocol=JSON.parse(await fs.readFile(new URL('protocol-v2.json',root),'utf8'));
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const context=await browser.newContext({httpCredentials:{username:credentials.username,password:credentials.password,origin:base,send:'always'},viewport:{width:1440,height:1100}});
await context.route(base+'/**',route=>route.continue({headers:{...route.request().headers(),authorization:'Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64')}}));
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const get=async path=>{const r=await context.request.get(base+'/backend/api/v1/jobs/'+path);if(!r.ok())throw Error('GET failed '+r.status());return r.json();};
const jobArg=process.argv.indexOf('--job');
const selected=jobArg>=0?protocol.sources.filter(s=>s.job===process.argv[jobArg+1]):protocol.sources;
if(!selected.length)throw Error('No matching source');
const errors=[],writes=[],results=[];
const page=await context.newPage();
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(!['GET','HEAD'].includes(r.method()))writes.push(r.method()+' '+new URL(r.url()).pathname);});
await page.addInitScript(()=>{window.__tones=0;const start=OscillatorNode.prototype.start;OscillatorNode.prototype.start=function(...args){window.__tones++;return start.apply(this,args)};});
try{
  await page.goto(base+'/structure-review-2026-11-15/',{waitUntil:'domcontentloaded'});
  for(const source of selected){
    const before=await get(source.job),saved=await get(source.job+'/root-practice');
    const originalRoot=JSON.parse(await fs.readFile(new URL(source.job+'/root-before.json',root),'utf8'));
    const originalScore=JSON.parse(await fs.readFile(new URL(source.job+'/score-before.json',root),'utf8'));
    const candidate=JSON.parse(await fs.readFile(new URL(source.job+'/run-fold0-original-demucs/candidate.json',root),'utf8'));
    await page.getByLabel('選擇歌曲').selectOption({label:source.title});
    if(!await page.locator('audio').evaluate(a=>a.paused))throw Error('Switching songs did not stop playback');
    await page.waitForFunction(()=>document.querySelector('audio').readyState>=1);
    const media=await page.locator('audio').evaluate(a=>({src:a.currentSrc,duration:a.duration,time:a.currentTime}));
    if(!media.src.includes(source.job)||Math.abs(media.duration-candidate.duration)>.05||media.time>.1)throw Error('Song switch retained a previous source or position');
    const rows=page.locator('.section');
    if(await rows.count()!==candidate.sections.length)throw Error('Missing real sections');
    const target=Math.min(2,candidate.sections.length-1),s=candidate.sections[target];
    await rows.nth(target).getByRole('button',{name:'聽這段',exact:true}).click();
    await page.waitForFunction(start=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>=start&&a.currentTime<start+3},s.start);
    const sectionTime=await page.locator('audio').evaluate(a=>{a.pause();return a.currentTime});
    await rows.nth(target).getByRole('button',{name:'聽交界',exact:true}).click();
    const boundaryStart=Math.max(0,s.start-3);
    await page.waitForFunction(start=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>=start&&a.currentTime<start+2},boundaryStart);
    await page.waitForFunction(()=>document.querySelector('audio').paused,{},{timeout:12000});
    const boundaryEnd=await page.locator('audio').evaluate(a=>a.currentTime);
    if(Math.abs(boundaryEnd-Math.min(candidate.duration,s.start+3))>.6)throw Error('Boundary stop is outside expected range');
    for(const width of [320,390,768,1440]){
      await page.setViewportSize({width,height:1100});
      if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Overflow '+width);
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.screenshot({fullPage:true,path:new URL(source.job+'-'+width+'.png',root).pathname});
    }
    const after=await get(source.job),savedAfter=await get(source.job+'/root-practice');
    if(hash(saved)!==hash(savedAfter)||hash(before.score)!==hash(after.score))throw Error('Practice or Score changed during review');
    if(hash(saved)!==hash(originalRoot)||hash(before.score)!==hash(originalScore))throw Error('Practice or Score differs from pre-inference snapshot');
    if(await page.locator('#error').innerText())throw Error('Audio error shown');
    results.push({job:source.job,title:source.title,section_count:candidate.sections.length,section_time:sectionTime,boundary_start:boundaryStart,boundary_stopped_at:boundaryEnd,widths:[320,390,768,1440],practice_unchanged:true,score_unchanged:true,oscillators:await page.evaluate(()=>window.__tones),switch_loaded_correct_source:true});
    if(source!==selected.at(-1)){
      await rows.nth(target).getByRole('button',{name:'聽這段',exact:true}).click();
      await page.waitForFunction(()=>!document.querySelector('audio').paused);
    }
  }
  if(errors.length||writes.length)throw Error(JSON.stringify({errors,writes}));
  await fs.writeFile(new URL(jobArg>=0?'browser-'+selected[0].job+'.json':'browser.json',root),JSON.stringify({results,errors,writes},null,2)+'\n');
  console.log(JSON.stringify({results,errors,writes},null,2));
}finally{await browser.close()}
