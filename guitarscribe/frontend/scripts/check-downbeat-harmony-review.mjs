// Verify the real authenticated A/B page, including same-position switching.
import {chromium,expect} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';
const base=process.argv[2],output=process.argv[3];
const auth=JSON.parse(await readFile(process.env.GUITARSCRIBE_WEB_ACCESS_FILE,'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const errors=[],widths=[];
try{
 const anon=await browser.newContext({extraHTTPHeaders:{'ngrok-skip-browser-warning':'1'}});
 expect((await anon.request.get(base+'/harmony-review-2026-11-01/')).status()).toBe(401);await anon.close();
 const context=await browser.newContext({httpCredentials:auth,extraHTTPHeaders:{'ngrok-skip-browser-warning':'1'}});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/harmony-review-2026-11-01/');
 for(const width of [320,390,1440]){
  await page.setViewportSize({width,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);widths.push(width);
 }
 await expect.poll(()=>page.locator('audio').evaluateAll(els=>els.every(e=>e.duration===40&&!e.error)),{timeout:30000}).toBe(true);
 await page.getByRole('button',{name:'同位置聽 A',exact:true}).click();
 await expect.poll(()=>page.locator('#a').evaluate(e=>e.currentTime)).toBeGreaterThan(.1);
 await page.locator('#a').evaluate(e=>{e.pause();e.currentTime=12.25;});
 await page.getByRole('button',{name:'同位置聽 B',exact:true}).click();
 await expect(page.locator('#switch-b')).toHaveAttribute('aria-pressed','true');
 const switched=await page.locator('#b').evaluate(e=>e.currentTime);
 expect(switched).toBeGreaterThanOrEqual(12.25);expect(switched).toBeLessThan(13.25);
 expect(await page.locator('#a').evaluate(e=>e.paused)).toBe(true);
 await page.evaluate(()=>{document.querySelector('#switch-a').click();document.querySelector('#switch-b').click();});
 await expect(page.locator('#switch-b')).toHaveAttribute('aria-pressed','true');
 await expect.poll(()=>page.locator('audio').evaluateAll(els=>els.filter(e=>!e.paused).length)).toBe(1);
 await page.getByText('需要時：原曲或單獨吉他',{exact:true}).click();
 await page.getByLabel('原曲',{exact:true}).evaluate(e=>e.play());
 expect(await page.locator('#b').evaluate(e=>e.paused)).toBe(true);
 await page.locator('audio').evaluateAll(els=>els.forEach(e=>e.pause()));
 await expect(page.locator('#status')).toContainText('已暫停');
 await expect(page.locator('#status')).not.toContainText('目前無法播放');
 await page.getByText('需要時：原曲或單獨吉他',{exact:true}).click();
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:output+'/review-mobile.png',fullPage:true});
 expect(errors).toEqual([]);
 const report={widths,noOverflow:true,allFiveDurations:40,exclusivePlayback:true,samePositionSwitch:switched,rapidSwitch:true,anonymousDenied:true,errors};
 await writeFile(output+'/public-review.json',JSON.stringify(report,null,2));console.log(report);
}finally{await browser.close();}
