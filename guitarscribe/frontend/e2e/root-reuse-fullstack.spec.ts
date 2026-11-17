import {test,expect} from '@playwright/test';
const endpoint='/backend/api/v1/jobs/reuse-fixture/root-practice';
test('real saved roots compare, audition source only, reuse, export, reload and undo while retaining another edit',async({page,request})=>{
 const audioRequests:string[]=[];page.on('request',r=>{if(r.url().includes('/audio?'))audioRequests.push(r.url());});
 await page.addInitScript(()=>{(window as any).sounds=[];for(const [kind,prototype] of [['tone',OscillatorNode.prototype],['source',AudioBufferSourceNode.prototype]] as const){const start=prototype.start;prototype.start=function(...args:any[]){(window as any).sounds.push({kind,offset:args[1],duration:args[2]});return (start as any).apply(this,args);};}});
 await page.goto('/?practice=roots&job=reuse-fixture');await page.getByText('比較重複段與沿用',{exact:true}).click();
 await page.getByRole('button',{name:'聽來源核心',exact:true}).click();await expect.poll(()=>page.evaluate(()=>(window as any).sounds.length)).toBe(1);
 await page.getByRole('button',{name:'聽目標核心',exact:true}).click();await expect.poll(()=>page.evaluate(()=>(window as any).sounds.length)).toBe(2);
 expect(audioRequests.length).toBeGreaterThan(0);expect(audioRequests.every(url=>url.includes('/song-structure/audio?')&&url.includes('audio_sha256='))).toBe(true);
 expect(await page.evaluate(()=>(window as any).sounds)).toEqual([{kind:'source',offset:0,duration:8},{kind:'source',offset:8,duration:8}]);
 await page.getByRole('button',{name:'暫停播放',exact:true}).click();await page.getByRole('button',{name:'播放原曲範圍',exact:true}).click();await expect.poll(()=>page.evaluate(()=>(window as any).sounds.length)).toBe(3);
 expect(audioRequests.every(url=>url.includes('/song-structure/audio?')&&url.includes('audio_sha256='))).toBe(true);
 await page.getByLabel('我已回聽並確認兩個核心的拍位與根音可對應').check();await page.getByRole('button',{name:'預覽可沿用位置',exact:true}).click();await expect(page.getByLabel('沿用位置預覽')).toContainText('保留目前判斷');
 await page.screenshot({path:'/tmp/guitarscribe-root-reuse-fullstack.png',fullPage:true});
 const before=await (await request.get(endpoint)).json();await page.getByRole('button',{name:'沿用選取的 1 格',exact:true}).click();await expect(page.getByLabel('根音保存狀態')).toHaveText('已保存');
 const applied=await (await request.get(endpoint)).json();expect(applied.version).toBe(before.version+1);expect(applied.document.segments[2].root).toBe(0);expect(applied.document.segments[3]).toEqual(before.document.segments[3]);
 await expect(page.getByLabel('結構譜與工作量')).toContainText('有效沿用 1');const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'下載結構譜 JSON',exact:true}).click()]);const stream=await download.createReadStream();let text='';for await(const c of stream!)text+=c.toString();const exported=JSON.parse(text);expect(exported.expanded_order.map((s:any)=>s.id)).toEqual(['s0','s1','s2']);expect(exported.expanded_order[1].references[0].state).toBe('已確認沿用');
 // A later edit outside the reused targets must survive batch undo.
 applied.document.segments[5].root=2;applied.document.segments[5].status='confirmed';expect((await request.put(endpoint,{data:{expected_version:applied.version,document:applied.document}})).ok()).toBe(true);
 await page.reload();await page.getByText('比較重複段與沿用',{exact:true}).click();await page.getByRole('button',{name:'撤銷這批沿用',exact:true}).click();await expect(page.getByLabel('根音保存狀態')).toHaveText('已保存');
 const undone=await (await request.get(endpoint)).json();expect(undone.document.segments[2]).toEqual(before.document.segments[2]);expect(undone.document.segments[5].root).toBe(2);
 expect(await (await request.get('/backend/fixture/invariants')).json()).toEqual({structure_unchanged:true,score_unchanged:true});
});
test('real stale plan is rejected after another client changes its source',async({page,request})=>{
 await page.goto('/?practice=roots&job=reuse-fixture');await page.getByText('比較重複段與沿用',{exact:true}).click();await page.getByLabel('我已回聽並確認兩個核心的拍位與根音可對應').check();await page.getByRole('button',{name:'預覽可沿用位置',exact:true}).click();await expect(page.getByLabel('沿用位置預覽')).toBeVisible();
 const before=await (await request.get(endpoint)).json();before.document.segments[0].root=4;expect((await request.put(endpoint,{data:{expected_version:before.version,document:before.document}})).ok()).toBe(true);
 await page.getByRole('button',{name:'沿用選取的 1 格',exact:true}).click();await expect(page.getByLabel('根音保存狀態')).toContainText('版本');const after=await (await request.get(endpoint)).json();expect(after.document.segments[0].root).toBe(4);expect(after.document.segments[2].root).toBeNull();
});
