// Actual authenticated website: no audio uploads or edits to existing jobs.
import {chromium,expect} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';
const base=process.argv[2],output=process.argv[3];
const auth=JSON.parse(await readFile(process.env.GUITARSCRIBE_WEB_ACCESS_FILE,'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const errors=[],checks=[];
try{
 const anonymous=await browser.newContext({extraHTTPHeaders:{'ngrok-skip-browser-warning':'1'}});
 expect((await anonymous.request.get(base+'/review-2026-11-01/')).status()).toBe(401);
 await anonymous.close();
 const context=await browser.newContext({httpCredentials:auth,extraHTTPHeaders:{'ngrok-skip-browser-warning':'1'}});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/review-2026-11-01/');
 for(const width of [320,390,1440]){
  await page.setViewportSize({width,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  checks.push({width,noOverflow:true});
 }
 await expect.poll(()=>page.locator('audio').first().evaluate(e=>e.duration),{timeout:30000}).toBe(40);
 await page.getByLabel('原曲加拍子',{exact:true}).evaluate(e=>e.play());
 await expect.poll(()=>page.getByLabel('原曲加拍子',{exact:true}).evaluate(e=>e.currentTime),{timeout:10000}).toBeGreaterThan(.1);
 await page.getByLabel('原曲加每小節一下的吉他',{exact:true}).evaluate(e=>e.play());
 expect(await page.getByLabel('原曲加拍子',{exact:true}).evaluate(e=>e.paused)).toBe(true);
 await expect.poll(()=>page.getByLabel('原曲加每小節一下的吉他',{exact:true}).evaluate(e=>e.currentTime)).toBeGreaterThan(.1);
 await page.locator('audio').evaluateAll(els=>els.forEach(e=>e.pause()));
 const waves=await page.locator('audio').evaluateAll(els=>els.map(e=>({src:e.getAttribute('src'),duration:e.duration,error:e.error?.message??null})));
 expect(waves.every(w=>w.duration===40&&!w.error)).toBe(true);
 expect(errors).toEqual([]);
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:output+'/review-mobile.png',fullPage:true});
 const report={checks,waves,anonymousDenied:true,exclusivePlayback:true,errors};
 await writeFile(output+'/public-review.json',JSON.stringify(report,null,2));console.log(report);
}finally{await browser.close();}
