// Read-only real-song verification. Never submit a practice decision.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const external=true;
const report=new URL('../../output/evaluation/cloud-personal-2026-11-20/',import.meta.url);await fs.mkdir(report,{recursive:true});
const access=JSON.parse(await fs.readFile(new URL('../../output/cloud-control/access.json',import.meta.url),'utf8'));
const deployment=JSON.parse(await fs.readFile(new URL('../../infra/on_demand/deployment.json',import.meta.url),'utf8'));
const base=external?deployment.url:'http://127.0.0.1:5273';
const authorization='Basic '+Buffer.from(access.username+':'+access.password).toString('base64');
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true}),context=await browser.newContext({viewport:{width:1440,height:1100},httpCredentials:{...access,origin:base,send:'always'}});
const writes=[],errors=[],results=[];
await context.route(base+'/**',r=>{if(!['GET','HEAD'].includes(r.request().method()) && new URL(r.request().url()).pathname !== '/backend/cloud/activity'){writes.push(new URL(r.request().url()).pathname);return r.abort();}return r.continue({headers:{...r.request().headers(),authorization}});});
await context.addInitScript(()=>{window.__tones=0;const start=OscillatorNode.prototype.start;OscillatorNode.prototype.start=function(...args){window.__tones++;return start.apply(this,args);};});
const get=async path=>{const r=await context.request.get(base+'/backend/api/v1/jobs/'+path);if(!r.ok())throw Error('GET '+r.status());return r.json();};
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
try{
 for(const job of ['84defcef7fd44bbc8a1024b24d65c78e','83a3643ab3814172a046cebf709f3413','a3be29912a7045448765290d7cba2f6c']){
  const before={score:(await get(job)).score,roots:await get(job+'/root-practice'),structure:await get(job+'/song-structure'),chords:await get(job+'/chord-practice')};
  const sections=before.structure.document.sections,target=sections.find(s=>s.label==='chorus')??sections[0];
  const url=base+'/?'+new URLSearchParams({practice:'chords',job,structure:target.id,structure_source:before.structure.document.source.fingerprint,section_start:String(target.start),section_end:String(target.end)});
  const page=await context.newPage();page.setDefaultTimeout(45000);page.on('pageerror',e=>errors.push(e.message));await page.goto(url,{waitUntil:'domcontentloaded'});
  await expect(page.getByLabel('雲端練習')).toBeVisible();
  await expect(page.getByRole('heading',{name:'已鎖定：'+target.display_label,exact:true})).toBeVisible();
  const chart=page.getByRole('slider',{name:'頻譜定位時間',exact:true});await expect(chart).toHaveAttribute('aria-valuemin',String(target.start));await expect(chart).toHaveAttribute('aria-valuemax',String(target.end));
  await page.getByRole('button',{name:'產生低頻圖',exact:true}).click();await expect(page.getByLabel('頻譜狀態')).toContainText('低頻圖已就緒',{timeout:120000});
  const colors=await page.locator('canvas').evaluate(c=>{const data=c.getContext('2d').getImageData(0,0,c.width,c.height).data,s=new Set();for(let i=0;i<data.length;i+=16)s.add(data.slice(i,i+3).join(','));return s.size;});if(colors<20)throw Error('Empty spectrum');
  const rows=page.getByLabel('鎖定段落和弦清單').getByRole('button');const count=await rows.count();const expected=before.chords.document.segments.filter(s=>s.start<target.end&&s.end>target.start).length;expect(count).toBe(expected);
  const first=before.chords.document.segments.find(s=>s.start<target.end&&s.end>target.start);await rows.first().click();await expect(page.getByLabel('和弦開始秒數')).toHaveValue(String(Math.max(first.start,target.start)));
  await page.getByRole('button',{name:'播放原曲範圍',exact:true}).click();await page.waitForFunction(start=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>=start&&a.currentTime<start+5;},target.start);await page.getByRole('button',{name:'暫停原曲',exact:true}).click();
  for(const width of [1440,390]){await page.setViewportSize({width,height:1100});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:new URL(`${external?'external':'local'}-${job}-${width}.png`,report).pathname,fullPage:true});}
  expect(await page.evaluate(()=>window.__tones)).toBe(0);
  const after={score:(await get(job)).score,roots:await get(job+'/root-practice'),structure:await get(job+'/song-structure'),chords:await get(job+'/chord-practice')};expect(hash(after)).toBe(hash(before));
  results.push({job,sections:sections.length,section:target.display_label,start:target.start,end:target.end,visible_chords:count,total_chords:before.chords.document.segments.length,chord_version:before.chords.version,spectrum_colors:colors,unchanged:true});await page.close();
 }
 expect(writes).toEqual([]);expect(errors).toEqual([]);const result={base,results,writes,errors};await fs.writeFile(new URL(external?'external-browser.json':'local-browser.json',report),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
}finally{await browser.close();}
