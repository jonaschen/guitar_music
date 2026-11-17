// Read-only deployed mobile demonstration check. Refuse every write request.
import {chromium,devices,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const report=new URL('../../output/evaluation/mobile-demo-2026-11-17/',import.meta.url);
await fs.mkdir(report,{recursive:true});
const external=process.argv.includes('--external');
const deployment=JSON.parse(await fs.readFile(new URL('../../output/web-preview/mobile-deployment.json',import.meta.url),'utf8'));
const base=external?deployment.url:'http://127.0.0.1:5273';
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const authorization='Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64');
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const context=await browser.newContext({...devices['Pixel 7'],httpCredentials:{...credentials,origin:base,send:'always'}});
const writes=[],errors=[],results=[],audio=[];
await context.route(base+'/**',route=>{
 if(!['GET','HEAD'].includes(route.request().method())){writes.push(route.request().method()+' '+new URL(route.request().url()).pathname);return route.abort();}
 return route.continue({headers:{...route.request().headers(),authorization}});
});
await context.addInitScript(()=>{window.__tones=0;const start=OscillatorNode.prototype.start;OscillatorNode.prototype.start=function(...args){window.__tones++;return start.apply(this,args);};});
const get=async path=>{const r=await context.request.get(base+'/backend/api/v1/jobs/'+path);if(!r.ok())throw Error('GET failed '+r.status());return r.json();};
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
try{
 for(const job of (external?['83a3643ab3814172a046cebf709f3413']:['83a3643ab3814172a046cebf709f3413','84defcef7fd44bbc8a1024b24d65c78e','a3be29912a7045448765290d7cba2f6c'])){
  const score=await get(job),saved=await get(job+'/song-structure'),roots=await get(job+'/root-practice');
  const document=saved.document??(await get(job+'/song-structure/analysis')).candidate;
  const page=await context.newPage();page.setDefaultTimeout(45000);page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(new URL(r.url()).pathname.endsWith('/audio'))audio.push({path:new URL(r.url()).pathname,status:r.status()});});
  await page.goto(base+'/?practice=demo&job='+job,{waitUntil:'domcontentloaded'});
  await expect(page.getByRole('heading',{name:score.score.song.title,exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:/^介紹第 /})).toHaveCount(document.sections.length);
  await page.screenshot({path:new URL(`${external?'external':'local'}-${job}-structure.png`,report).pathname,fullPage:true});
  const i=Math.max(0,document.sections.findIndex(s=>s.label==='chorus'));const section=document.sections[i];
  await page.getByRole('button',{name:`介紹第 ${i+1} 段 ${section.display_label}`,exact:true}).tap();
  await page.getByRole('button',{name:'下一步：聽這一段',exact:true}).tap();await page.getByRole('button',{name:'播放選定段落',exact:true}).tap();
  await page.waitForFunction(start=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>start+.1&&a.currentTime<start+5;},section.start,{timeout:60000});
  const played=await page.locator('audio').evaluate(a=>({time:a.currentTime,src:a.currentSrc}));
  if(!played.src.includes(document.source.audio_sha256))throw Error('Wrong recording hash');
  await page.getByRole('button',{name:'暫停原曲',exact:true}).tap();
  await page.screenshot({path:new URL(`${external?'external':'local'}-${job}-listen.png`,report).pathname,fullPage:true});
  await page.getByRole('button',{name:'下一步：看低頻圖',exact:true}).tap();
  {await page.getByRole('button',{name:'產生低頻圖',exact:true}).tap();await expect(page.getByLabel('頻譜狀態')).toContainText('低頻圖已就緒',{timeout:120000});
   const colors=await page.locator('canvas').evaluate(c=>{const rgba=c.getContext('2d').getImageData(0,0,c.width,c.height).data,result=new Set();for(let i=0;i<rgba.length;i+=16)result.add(rgba.slice(i,i+3).join(','));return result.size;});if(colors<20)throw Error('Empty frequency image');
  }
  for(const size of [{width:390,height:844},{width:844,height:390}]){await page.setViewportSize(size);if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Mobile overflow');}
  await page.setViewportSize({width:390,height:844});await page.getByRole('slider',{name:'頻譜定位時間',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:new URL(`${external?'external':'local'}-${job}-spectrum.png`,report).pathname,fullPage:false});
  if(await page.evaluate(()=>window.__tones)!==0)throw Error('Unexpected synthesized tone');
  if(hash(await get(job+'/root-practice'))!==hash(roots)||hash(await get(job+'/song-structure'))!==hash(saved)||hash((await get(job)).score)!==hash(score.score))throw Error('Practice changed during demo');
  results.push({job,title:score.score.song.title,sections:document.sections.length,candidate_only:!saved.document,played_at:played.time,spectrum_verified:true,roots_version:roots.version,progress_unchanged:true});await page.close();
 }
 if(writes.length||errors.length)throw Error(JSON.stringify({writes,errors}));
 const record={base,results,writes,errors,audio};await fs.writeFile(new URL(external?'external-browser.json':'local-browser.json',report),JSON.stringify(record,null,2));console.log(JSON.stringify(record,null,2));
}finally{await browser.close();}
