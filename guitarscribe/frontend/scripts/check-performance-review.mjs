// Public production smoke: real API, source audio, save/reload, responsive notation.
import {chromium,expect} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';
const root=process.argv[2],base=process.argv[3];
const auth=JSON.parse(await readFile(process.env.GUITARSCRIBE_WEB_ACCESS_FILE,'utf8'));
const rows=JSON.parse(await readFile(root+'/published-revisions.json','utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const errors=[],checks=[];
try{
 const page=await browser.newPage({httpCredentials:auth,extraHTTPHeaders:{'ngrok-skip-browser-warning':'1'},viewport:{width:390,height:844}});
 page.on('pageerror',e=>errors.push(e.message));
 // Verify the scheduled source offset rather than sampling a sub-second chord
 // label after a potentially delayed remote browser assertion.
 await page.addInitScript(()=>{
  window.__reviewSourceStarts=[];
  const start=AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start=function(...args){if(this.buffer?.duration>20)window.__reviewSourceStarts.push({offset:args[1]??0});return start.apply(this,args);};
 });
 await page.goto(base+'/?job='+rows[0].job);
 await expect(page.getByLabel('和弦時間表',{exact:true}).getByRole('button')).toHaveCount(143,{timeout:30000});
 const boxes=await page.getByLabel('和弦時間表',{exact:true}).getByRole('button').evaluateAll(els=>els.slice(0,3).map(el=>{const b=el.getBoundingClientRect();return {x:b.x,y:b.y}}));
 expect(boxes[0].x).toBe(boxes[1].x);expect(boxes[1].y).toBeLessThan(boxes[2].y);
 await page.getByText('練習與編輯',{exact:true}).click();
 const saved=page.waitForResponse(r=>r.url().endsWith('/revisions')&&r.request().method()==='POST',{timeout:30000});
 await page.getByRole('button',{name:'整理演奏稿',exact:true}).click();
 await expect(page.locator('.performance-draft-status')).toContainText('已整理',{timeout:30000});
 const revision=(await(await saved).json()).revision_id;
 const score=await page.evaluate(async id=>await(await fetch('/backend/revisions/'+id)).json(),revision);
 expect(score.provenance.parameters.performance_voicings_repaired).toBe(17);
 const compiled=await page.evaluate(async score=>await(await fetch('/backend/scores/playback/manifest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(score)})).json(),score);
 expect(compiled.events.filter(e=>e.track==='guitar'&&e.pitches.length===1)).toHaveLength(0);
 await page.getByRole('button',{name:'播放 31.35 秒的 C/E',exact:true}).click();
 await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible({timeout:90000});
 await expect(page.getByLabel('跟彈提示',{exact:true})).toBeVisible();
 const starts=await page.evaluate(()=>window.__reviewSourceStarts);
 expect(starts.at(-1).offset).toBeCloseTo(31.346938775,2);
 await page.getByRole('button',{name:'暫停',exact:true}).click();
 await page.screenshot({path:root+'/public-timeline.png'});
 await page.reload();await expect(page.locator('.chord-timeline button')).toHaveCount(143,{timeout:30000});
 await page.getByText('練習與編輯',{exact:true}).click();
 await expect(page.locator('.performance-draft-status')).toContainText('已整理');
 checks.push({case:'timeline',revision,fullVoicings:true,savedAndReloaded:true,mixedPlayback:true,sourceOffset:starts.at(-1).offset});
 await page.goto(base+'/?revision='+rows[1].revisions.b);
 await expect(page.getByLabel('Bar 2',{exact:true})).toBeVisible({timeout:30000});
 await expect(page.getByRole('button',{name:'播放 Bar 2 的 F',exact:true})).toHaveCount(0);
 await expect(page.getByLabel('Bar 2',{exact:true}).getByText('3.5 拍',{exact:true})).toBeVisible();
 await expect(page.getByLabel('Bar 2',{exact:true}).getByText('0.5 拍',{exact:true})).toBeVisible();
 const tops=await page.locator('.notation-measure').evaluateAll(els=>els.slice(0,4).map(el=>el.getBoundingClientRect().top));
 expect(tops[0]).toBe(tops[1]);expect(tops[2]).toBe(tops[3]);expect(tops[2]).toBeGreaterThan(tops[0]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'播放',exact:true}).click();
 await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible({timeout:90000});
 await page.getByRole('button',{name:'暫停',exact:true}).click();
 await page.locator('.notation-measure').nth(6).scrollIntoViewIfNeeded();await page.screenshot({path:root+'/public-metered.png'});
 checks.push({case:'metered',twoBarsPerRow:true,boundaryFragmentRemoved:true,mixedPlayback:true});
 expect(errors).toEqual([]);
 await writeFile(root+'/public-browser.json',JSON.stringify({checks,errors},null,2));console.log(JSON.stringify({checks,errors}));
}finally{await browser.close();}
