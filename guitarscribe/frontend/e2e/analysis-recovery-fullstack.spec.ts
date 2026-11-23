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
