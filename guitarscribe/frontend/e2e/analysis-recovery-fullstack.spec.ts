import {test,expect} from '@playwright/test';

test('server restart recovery survives a lost POST reply and keeps the original work',async({page,request,browserName})=>{
 const job=`interrupted-${browserName}`,base='/backend/api/v1/jobs/';
 const original=await (await request.get(base+job)).json();
 expect(original.status).toBe('failed');expect(original.can_retry).toBe(true);
 let posts=0;const children:string[]=[];
 await page.route(`**/api/v1/jobs/${job}/retry`,async route=>{
  posts++;const response=await route.fetch();expect(response.status()).toBe(202);
  children.push((await response.json()).id);
  if(posts===1)return route.abort('failed');
  return route.fulfill({response});
 });
 await page.goto('/?job='+job);
 await page.getByRole('button',{name:'用保留音檔重新分析',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('可再按一次查回同一工作');
 await page.getByRole('button',{name:'用保留音檔重新分析',exact:true}).click();
 await expect(page.getByRole('heading',{name:'中斷後的練習歌',exact:true})).toBeVisible();
 expect(children).toHaveLength(2);expect(children[0]).toBe(children[1]);expect(children[0]).not.toBe(job);
 await page.reload();await expect(page.getByRole('heading',{name:'中斷後的練習歌',exact:true})).toBeVisible();
 expect((await request.get(base+children[0]+'/audio',{headers:{Range:'bytes=0-1023'}})).status()).toBe(206);
 expect(await (await request.get('/backend/fixture/invariants')).json()).toEqual({original_jobs_unchanged:true,original_files_unchanged:true});
 const completed=await (await request.get(base+children[0])).json();
 expect(completed.retry_of).toBe(job);expect(completed.can_retry).toBe(false);
 expect((await request.post(base+children[0]+'/retry')).status()).toBe(409);
});

test('capo advice applies its actual voicing path only after selection and preserves sounding chords',async({page,request,browserName})=>{
 const base='/backend',score={song:{title:`Capo practice ${browserName}`,duration_seconds:8},chords:[{id:'c',start:0,end:4,symbol:'C'},{id:'g',start:4,end:8,symbol:'G'}]};
 const created=await request.post(base+'/revisions',{data:{score,create_new:true}});expect(created.ok()).toBe(true);
 const originalId=(await created.json()).revision_id;
 const original=await (await request.get(base+'/revisions/'+originalId)).json();
 await page.goto('/?revision='+originalId);await page.getByText('比較較容易的 Capo 按法',{exact:true}).click();
 await page.getByLabel('建議最高 Capo').fill('0');await page.getByLabel('偏好把位').fill('8');
 const compared=page.waitForResponse(r=>r.url().endsWith('/scores/capo-recommendations')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'比較按法方案',exact:true}).click();
 const rows=await (await compared).json();expect(rows).toHaveLength(1);expect(rows[0].covered_chords).toBe(2);
 await expect(page.getByLabel('Capo 方案 0')).toContainText('完整按法 2 / 2');
 expect(await (await request.get(base+'/revisions/'+originalId)).json()).toEqual(original);
 const saved=page.waitForResponse(r=>r.url().endsWith('/revisions')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'採用 Capo 0',exact:true}).click();
 const newId=(await (await saved).json()).revision_id;
 const adopted=await (await request.get(base+'/revisions/'+newId)).json();
 expect(adopted.chords.map((c:any)=>[c.id,c.start,c.end,c.symbol])).toEqual(original.chords.map((c:any)=>[c.id,c.start,c.end,c.symbol]));
 expect(adopted.song).toEqual(original.song);expect(adopted.key_context.source).toEqual(original.key_context.source);
 for(const chord of adopted.chords)expect(chord.voicing_id).toBe(rows[0].voicing_plan[chord.id]);
 expect(newId).not.toBe(originalId);expect(await (await request.get(base+'/revisions/'+originalId)).json()).toEqual(original);
 await page.reload();await expect(page.getByRole('heading',{name:score.song.title,exact:true})).toBeVisible();
 expect(await (await request.get(base+'/revisions/'+newId)).json()).toEqual(adopted);
});
