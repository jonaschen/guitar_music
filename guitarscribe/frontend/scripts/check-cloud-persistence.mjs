// Operator-only: requires an ID seeded by verify_cloud_fixture.py on the VM.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const job=process.argv[2];if(!/^[a-f0-9]{32}$/.test(job??''))throw Error('Pass the owned cloud fixture ID');
const access=JSON.parse(await fs.readFile(new URL('../../output/cloud-control/access.json',import.meta.url),'utf8'));
const {url:base}=JSON.parse(await fs.readFile(new URL('../../infra/on_demand/deployment.json',import.meta.url),'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const context=await browser.newContext({httpCredentials:{...access,origin:base,send:'always'}});
const authorization='Basic '+Buffer.from(access.username+':'+access.password).toString('base64');
const prefix='/backend/api/v1/jobs/'+job;
const get=async suffix=>{const r=await context.request.get(base+prefix+suffix);expect(r.ok()).toBe(true);return r.json();};
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
try{
 const original=await get('');expect(original.score.song.title).toBe('Cloud persistence verification (temporary)');
 const before={score:original.score,roots:await get('/root-practice'),structure:await get('/song-structure')};
 await context.route(base+'/**',async route=>{
  const r=route.request(),path=new URL(r.url()).pathname;
  if(!['GET','HEAD'].includes(r.method())&&path!==prefix+'/chord-practice'&&path!=='/backend/cloud/activity')throw Error('Unexpected mutation: '+path);
  await route.continue({headers:{...r.headers(),authorization}});
 });
 const page=await context.newPage();page.setDefaultTimeout(45000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/?practice=structure&job='+job);
 await page.getByRole('button',{name:'選取第 2 段 副歌',exact:true}).click();
 await page.getByRole('link',{name:'鎖定這段練和弦',exact:true}).click();
 await expect(page.getByRole('heading',{name:'已鎖定：副歌',exact:true})).toBeVisible();
 const other=await context.newPage();await other.goto(page.url());
 await expect(other.getByRole('heading',{name:'已鎖定：副歌',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'產生低頻圖',exact:true}).click();
 await expect(page.getByLabel('頻譜狀態')).toContainText('低頻圖已就緒');
 await page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();
 await page.getByLabel('和弦名稱',{exact:true}).fill('Am/C');
 await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();
 await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');
 let saved=await get('/chord-practice');expect(saved.version).toBe(1);
 expect(saved.document.segments[0]).toMatchObject({start:0,end:4,symbol:null,original_symbol:'C'});
 expect(saved.document.segments[1]).toMatchObject({start:4,end:6,symbol:'Am/C',original_symbol:'C'});
 await page.getByRole('button',{name:'復原和弦修改',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');
 expect((await get('/chord-practice')).document.segments.every(s=>s.symbol===null)).toBe(true);
 await page.getByRole('button',{name:'重做和弦修改',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');
 await page.reload();await expect(page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true})).toContainText('Am/C');
 await other.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();
 await other.getByLabel('和弦名稱',{exact:true}).fill('Dm');await other.getByRole('button',{name:'採用／更新和弦',exact:true}).click();
 await expect(other.getByRole('alert')).toContainText('版本已變動');saved=await get('/chord-practice');expect(saved.version).toBe(3);
 const after={score:(await get('')).score,roots:await get('/root-practice'),structure:await get('/song-structure')};expect(hash(after)).toBe(hash(before));expect(errors).toEqual([]);
 const result={job_id:job,saved_version:saved.version,saved_sha256:hash(saved),scope_unchanged:true,undo_redo:true,reload:true,stale_tab_conflict:true,errors};
 await fs.writeFile(new URL('../../output/cloud-control/persistence-before-restart.json',import.meta.url),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
