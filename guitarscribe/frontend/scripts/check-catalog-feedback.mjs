// Ensure human acceptance follows the reviewed audio, not just a song identity.
import {chromium,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
const [directory,slug]=process.argv.slice(2);assert.ok(directory);assert.match(slug,/^[a-z0-9-]+$/);
const out=path.join(directory,'feedback-check-2026-10-30');await mkdir(out,{recursive:true});
const url=`http://127.0.0.1:5173/listening/${slug}/`;
const packet=await(await fetch(url+'packet.json')).json();
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const checks=[],errors=[];
try{
 for(const variant of ['reviewed','changed_audio','changed_mode','missing_feedback','missing_workspaces']){
  const page=await browser.newPage({viewport:{width:390,height:844}});
  page.on('pageerror',e=>errors.push(e.message));
  if(variant==='changed_audio'||variant==='changed_mode'){
   const modified=structuredClone(packet);
   if(variant==='changed_audio')modified[0].audio.audio.mix.sha256='0'.repeat(64);
   else modified[0].kind='rhythmic';
   await page.route('**/packet.json',r=>r.fulfill({json:modified}));
  }
  if(variant==='missing_feedback')await page.route('**/feedback.json',r=>r.fulfill({status:404,body:''}));
  if(variant==='missing_workspaces')await page.route('**/workspaces.json',r=>r.fulfill({status:404,body:''}));
  await page.goto(url+'index.html');await expect(page.locator('#songs button')).toHaveCount(7);
  if(variant==='reviewed'||variant==='missing_workspaces'){
   await expect(page.locator('#summary')).toContainText('6 個來源');
   for(const row of packet){
    await page.locator(`#songs button[data-video="${row.video}"]`).click();
    const text=row.video==='5wq_uTMW0v8'?'本批最好':row.video==='WObbdwgB41c'?'和弦聽感較差':'大部分和弦可跟刷';
    await expect(page.locator('#verdict')).toContainText(text);
    await expect(page.locator('#warning')).toContainText('小節譜與連續刷奏仍待完善');
    await expect(page.locator('#chords button')).toHaveCount(row.chords.length);
    if(variant==='reviewed')await expect(page.locator('#score-link')).toBeVisible();else await expect(page.locator('#score-link')).toBeHidden();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   }
   await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
   await page.setViewportSize({width:1440,height:1000});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }else{
   await expect(page.locator('#verdict')).toContainText('尚未有相符的試聽驗收');
   await expect(page.locator('#songs button').first()).toContainText('待試聽');
   if(variant==='changed_audio'||variant==='changed_mode')await expect(page.locator('#score-link')).toBeHidden();
  }
  checks.push({variant,passed:true});await page.close();
 }
 assert.deepEqual(errors,[]);await writeFile(path.join(out,'report.json'),JSON.stringify({checks,errors},null,2));
 console.log(JSON.stringify({checks,errors}));
}finally{await browser.close();}
