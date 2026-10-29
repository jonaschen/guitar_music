import {chromium,expect} from '@playwright/test';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
const [directory]=process.argv.slice(2);assert.ok(directory);
const rows=JSON.parse(await readFile(path.join(directory,'workspaces.json'),'utf8'));
const overview=JSON.parse(await readFile(path.join(directory,'overview.json'),'utf8'));
const out=path.join(directory,'workspace-check');await mkdir(out,{recursive:true});
const api='http://127.0.0.1:8000',web='http://127.0.0.1:5173';
async function get(route){const r=await fetch(api+route);assert.equal(r.status,200);return r.json()}
async function post(route,data){return fetch(api+route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const errors=[],reports=[];
try{
 const page=await browser.newPage({viewport:{width:390,height:844}});
 page.on('pageerror',e=>errors.push(e.message));
 for(const row of rows){
  const original=await get('/revisions/'+row.revision),expected=overview.find(r=>r.video===row.video);
  const response=await post('/scores/playback/manifest',original);assert.equal(response.status,200);
  assert.deepEqual((await response.json()).events,expected.events);
  for(const route of ['/scores/midi','/scores/musicxml'])assert.equal((await post(route,original)).status,422);
  const text=await (await post('/scores/chordpro',original)).text();assert.ok(!text.includes('{tempo:')&&!text.includes('{time:'));
  await page.goto(web+'/?revision='+row.revision);
  await expect(page.getByLabel('和弦時間表',{exact:true}).getByRole('button')).toHaveCount(original.chords.length);
  await expect(page.getByRole('button',{name:'播放',exact:true})).toBeEnabled();
  const c=original.chords[Math.floor(original.chords.length/2)];
  for(const mode of ['mix','source','guitar']){
   await page.getByLabel('播放聲音',{exact:true}).selectOption(mode);
   await page.getByRole('button',{name:`播放 ${c.start.toFixed(2)} 秒的 ${c.symbol}`,exact:true}).click();
   await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible({timeout:30000});
   await expect.poll(()=>page.locator('.playback-status').textContent()).toContain('播放中');
   await page.getByRole('button',{name:'暫停',exact:true}).click();
  }
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(await get('/revisions/'+row.revision),original);
  reports.push({video:row.video,eventParity:true,mixSourceGuitarPlayed:true,noOverflow:true,originalUnchanged:true});
 }
 // Fork before editing: acceptance baselines and user's revision history remain untouched.
 const baseline=await get('/revisions/'+rows[0].revision);
 const fork=await (await post('/revisions',{score:baseline})).json();
 await page.goto(web+'/?revision='+fork.revision_id);
 const first=baseline.chords[0],second=baseline.chords[1];assert.equal(first.end,second.start);
 await page.getByText('練習與編輯',{exact:true}).click();
 await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
 await page.getByRole('button',{name:`編輯 ${first.start.toFixed(2)} 秒的 ${first.symbol}`,exact:true}).click();
 const end=Number((first.end+.25).toFixed(3));
 await page.getByLabel('結束時間（秒）',{exact:true}).fill(String(end));
 const save=page.waitForResponse(r=>r.url().endsWith('/revisions')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'套用時間',exact:true}).click();
 const saved=await (await save).json();assert.notEqual(saved.revision_id,fork.revision_id);
 const changed=await get('/revisions/'+saved.revision_id);
 assert.equal(changed.chords[0].end,end);assert.equal(changed.chords[1].start,end);
 assert.deepEqual(changed.beats,[]);assert.equal(changed.analysis.timing_status,'unmetered');
 const manifest=await (await post('/scores/playback/manifest',changed)).json();
 assert.equal(manifest.events[0].end,end);assert.equal(manifest.events[1].start,end);
 await page.getByRole('button',{name:'復原',exact:true}).click();
 await expect(page.getByRole('button',{name:`編輯 ${second.start.toFixed(2)} 秒的 ${second.symbol}`,exact:true})).toBeVisible();
 await page.getByRole('button',{name:'重做',exact:true}).click();
 await expect(page.getByRole('button',{name:`編輯 ${end.toFixed(2)} 秒的 ${second.symbol}`,exact:true})).toBeVisible();
 await page.goto(web+'/?revision='+saved.revision_id);
 await expect(page.getByRole('button',{name:`播放 ${end.toFixed(2)} 秒的 ${second.symbol}`,exact:true})).toBeVisible();
 await page.getByLabel('歌曲 Capo',{exact:true}).selectOption('2');
 await expect(page.getByLabel('歌曲 Capo',{exact:true})).toHaveValue('2');
 await page.getByLabel('播放聲音',{exact:true}).selectOption('guitar');
 await page.getByRole('button',{name:'播放',exact:true}).click();
 await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible({timeout:30000});
 await page.getByRole('button',{name:'暫停',exact:true}).click();
 await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
 await page.setViewportSize({width:1440,height:1000});
 await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
 assert.deepEqual(await get('/revisions/'+rows[0].revision),baseline);
 assert.deepEqual(errors,[]);
 const report={reports,edit:{fork:fork.revision_id,saved:saved.revision_id,sharedBoundary:true,manifestMatchesEdit:true,undoRedo:true,reloaded:true,capoPlayback:true,baselineUnchanged:true},errors};
 await writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close()}
