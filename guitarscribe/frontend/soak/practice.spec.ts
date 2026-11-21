import {test,expect} from '@playwright/test';
// Dedicated, opt-in duration run against disposable API data, never personal songs.
test('ten-minute edit/reload/play cycle retains decisions and source boundaries',async({page,request})=>{
 const duration=Number(process.env.GUITARSCRIBE_SOAK_MS??600000);test.setTimeout(duration+120000);
 const base='/backend/api/v1/jobs/fixture-song';const structure=await (await request.get(base+'/song-structure')).json();
 const url='/?practice=chords&job=fixture-song&structure=chorus&structure_source='+structure.current_source.fingerprint+'&section_start=4&section_end=10';
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 let writes=0;const started=Date.now();const heaps:number[]=[];
 while(Date.now()-started<duration){
  await page.goto(url);await expect(page.getByLabel('和弦名稱',{exact:true})).toBeVisible();
  await page.getByLabel('和弦開始秒數').fill('4');await page.getByLabel('和弦結束秒數').fill('6');
  const symbol=writes%2?'Am/C':'G7';await page.getByLabel('和弦名稱',{exact:true}).fill(symbol);
  await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();
  await expect.poll(async()=>{const s=await (await request.get(base+'/chord-practice')).json();return s.document.segments.find((r:any)=>r.start===4)?.symbol;}).toBe(symbol);writes++;
  await page.getByRole('button',{name:'播放原曲範圍',exact:true}).click();await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeGreaterThan(4.2);
  expect(await page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeLessThan(6.1);
  await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(true);
  await page.reload();await expect(page.getByLabel('鎖定段落和弦清單')).toContainText(symbol);
  const result=await (await request.get('/backend/fixture/invariants')).json();expect(result).toEqual({root_unchanged:true,structure_unchanged:true,score_unchanged:true});
  const heap=await page.evaluate(()=>(performance as any).memory?.usedJSHeapSize??0);heaps.push(heap);
  expect(errors).toEqual([]);await page.waitForTimeout(Math.min(15000,Math.max(0,duration-(Date.now()-started))));
 }
 await test.info().attach('soak-summary',{body:JSON.stringify({elapsed_ms:Date.now()-started,cycles:writes,page_errors:errors,heap_bytes:heaps,source:'disposable fixture; no personal recordings'}),contentType:'application/json'});
 expect(writes).toBeGreaterThan(10);
});
