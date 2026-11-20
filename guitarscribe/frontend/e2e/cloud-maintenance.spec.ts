import {test,expect} from '@playwright/test';
import {fileURLToPath} from 'node:url';
test('cloud backup summary distinguishes pending edits and failure from saved progress',async({page})=>{
 let backup:any={state:'pending',last_success_at:1795212000,snapshot_at:1795211900};
 await page.route('http://cloud.test/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/')return route.fulfill({contentType:'text/html',body:'<!doctype html><meta charset="utf-8"><title>Fixture</title><main>練習稿已保存</main>'});
  if(path==='/cloud/status')return route.fulfill({json:{state:'running',stop_at:Date.now()/1000+3600}});
  if(path==='/backend/cloud/library')return route.fulfill({json:{songs:[]}});
  if(path==='/backend/cloud/maintenance')return route.fulfill({json:{backup,disk_low:false}});
  return route.fulfill({json:{ok:true}});
 });
 await page.goto('http://cloud.test/');
 await page.addScriptTag({path:fileURLToPath(new URL('../../infra/on_demand/cloud_toolbar.js',import.meta.url))});
 await expect(page.getByLabel('雲端備份狀態')).toContainText('新修改等待備份');
 await page.getByText('保存與備份',{exact:true}).click();
 await expect(page.getByText('最近完成備份：',{exact:false})).toBeVisible();
 backup={...backup,state:'failed'};await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
 await expect(page.getByLabel('雲端備份狀態')).toContainText('備份失敗');
 await expect(page.getByText('練習稿已保存',{exact:true})).toBeVisible();
 backup={...backup,state:'complete'};await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
 await expect(page.getByLabel('雲端備份狀態')).toHaveText('已完成備份');
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
