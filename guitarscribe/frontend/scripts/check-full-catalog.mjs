import {chromium,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
const [directory,slug]=process.argv.slice(2);assert.ok(directory);assert.match(slug,/^[a-z0-9-]+$/);
const rows=JSON.parse(await readFile(path.join(directory,'render-report.json'),'utf8'));
assert.equal(rows.length,7);
const out=path.join(directory,'browser-check');await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const reports=[],errors=[];
try{
 const page=await browser.newPage({viewport:{width:390,height:844}});
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`http://127.0.0.1:5173/listening/${slug}/index.html`);
 await expect(page.locator('#songs button')).toHaveCount(7);
 await expect(page.locator('#summary')).toContainText('7 個完整來源已處理');
 await expect(page.locator('audio')).toHaveCount(1);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 for(const row of rows){
  await page.locator(`#songs button[data-video="${row.video}"]`).click();
  await page.waitForFunction(expected=>{const a=document.querySelector('audio');return a.readyState>=1&&Math.abs(a.duration-expected)<.02},row.duration+.35);
  await expect(page.locator('#chords button')).toHaveCount(row.chords.length);
  await page.locator('audio').evaluate(a=>a.play());
  await page.waitForFunction(()=>document.querySelector('audio').currentTime>.1);
  await page.locator('audio').evaluate(a=>a.pause());
  if(row.kind==='unmetered'){
   await expect(page.locator('#warning')).toContainText('小節譜與連續刷奏仍待完善');
   await expect(page.locator('#score-link')).toHaveText('開啟可編輯和弦時間表');
   await expect(page.locator('#score-link')).toHaveAttribute('href',/revision=/);
  }
  await page.locator('audio').evaluate(a=>{a.currentTime=30});
  await page.locator('#mode').selectOption('source');
  await page.waitForFunction(()=>{const a=document.querySelector('audio');return a.readyState>=1&&Math.abs(a.currentTime-30)<.1&&a.paused});
  await page.locator('audio').evaluate(a=>a.play());
  await page.waitForFunction(()=>document.querySelector('audio').currentTime>30.1);
  const before=await page.locator('audio').evaluate(a=>a.currentTime);
  await page.locator('#mode').selectOption('guitar');
  await page.waitForFunction(time=>{const a=document.querySelector('audio');return !a.paused&&a.readyState>=2&&a.currentTime>=time},before);
  await page.locator('audio').evaluate(a=>a.pause());
  const index=Math.floor(row.chords.length/2),start=row.chords[index].start;
  await page.locator('#chords button').nth(index).click();
  await page.waitForFunction(t=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>=t-.05&&a.currentTime<t+2},start);
  await page.locator('audio').evaluate(a=>a.pause());
  await expect(page.locator('#error')).toBeEmpty();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  reports.push({video:row.video,duration:row.duration+.35,chords:row.chords.length,mode:row.kind,
   mixSourceAndGuitarPlayed:true,switchPreservesPositionAndState:true,chordSeek:true,mobileOverflow:false});
 }
 await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
 await page.setViewportSize({width:1440,height:1000});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
 assert.deepEqual(errors,[]);await writeFile(path.join(out,'report.json'),JSON.stringify({reports,errors},null,2));
 console.log(JSON.stringify({reports,errors}));
}finally{await browser.close();}
