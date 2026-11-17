import {test,expect} from '@playwright/test';
test('real section entry, clipped chord save, reload, CAS conflict and undo preserve structure roots and Score',async({page,context,request})=>{
 const base='/backend/api/v1/jobs/fixture-song',get=async(p:string)=>(await (await request.get(base+p)).json());
 const before=await get('/chord-practice');expect(before.version).toBe(0);
 await page.goto('/?practice=structure&job=fixture-song');await page.getByRole('button',{name:'選取第 2 段 副歌',exact:true}).click();await page.getByRole('link',{name:'鎖定這段練和弦',exact:true}).click();await expect(page.getByRole('heading',{name:'已鎖定：副歌',exact:true})).toBeVisible();
 const other=await context.newPage();await other.goto(page.url());await expect(other.getByRole('heading',{name:'已鎖定：副歌',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'產生低頻圖',exact:true}).click();await expect(page.getByLabel('頻譜狀態')).toContainText('低頻圖已就緒');
 await page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();await page.getByLabel('和弦名稱',{exact:true}).fill('Am/C');await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');
 const saved=await get('/chord-practice');expect(saved.version).toBe(1);expect(saved.document.segments[0]).toMatchObject({start:0,end:4,symbol:null,original_symbol:'C'});expect(saved.document.segments[1]).toMatchObject({start:4,end:6,symbol:'Am/C',original_symbol:'C'});
 await page.getByRole('button',{name:'復原和弦修改',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');expect((await get('/chord-practice')).document.segments.every((s:any)=>s.symbol===null)).toBe(true);
 await page.getByRole('button',{name:'重做和弦修改',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');await page.reload();await expect(page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true})).toContainText('Am/C');
 await other.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();await other.getByLabel('和弦名稱',{exact:true}).fill('Dm');await other.getByRole('button',{name:'採用／更新和弦',exact:true}).click();await expect(other.getByRole('alert')).toContainText('版本已變動');expect((await get('/chord-practice')).version).toBe(3);
 await page.getByRole('button',{name:'播放原曲範圍',exact:true}).click();await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeGreaterThanOrEqual(4);await page.getByRole('button',{name:'暫停原曲',exact:true}).click();
 const history=await get('/chord-practice/history');expect(history.map((s:any)=>s.version)).toEqual([2,1]);
 expect(await (await request.get('/backend/fixture/invariants')).json()).toEqual({root_unchanged:true,structure_unchanged:true,score_unchanged:true});await other.close();
});
