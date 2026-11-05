import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const base='http://127.0.0.1:4181',job='1b4158f1acee4beaa9af7cb42f3f52a0';
const out=new URL('../../output/evaluation/key-notes-2026-11-06/',import.meta.url);
const credentials=JSON.parse(await readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
  const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();let revisionAttempts=0,transposed,compiled;
  await page.route('**/revisions',r=>{revisionAttempts++;return r.fulfill({json:{revision_id:'isolated-verification'}});});
  await page.route('**/scores/transpose',async r=>{const response=await r.fetch();transposed=await response.json();await r.fulfill({response});});
  await page.route('**/scores/playback/manifest',r=>{compiled=r.request().postDataJSON();return r.continue();});
  await page.route(`${base}/backend/**`,r=>r.fallback({headers:{...r.request().headers(),authorization:'Basic '+Buffer.from(`${credentials.username}:${credentials.password}`).toString('base64')}}));
  await page.goto(`${base}/?job=${job}&timingView=auto`);await page.getByLabel('局部小節預覽',{exact:true}).waitFor();
  await page.getByLabel('歌曲調性',{exact:true}).selectOption('G');
  await page.waitForFunction(()=>document.querySelector('select[aria-label="播放聲音"]')?.value==='guitar');
  assert.deepEqual(transposed.key_context.source,{key:'B',mode:'minor'});assert.deepEqual(transposed.key_context.target,{key:'G',mode:'minor'});
  await page.getByRole('button',{name:'播放',exact:true}).click();await page.getByRole('button',{name:'暫停',exact:true}).waitFor();
  await page.screenshot({path:new URL('transposed-guitar-playing-390.png',out).pathname});
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  assert.equal(compiled.key_context.audio_matches_notation,false);assert.equal(compiled.key_context.transpose_semitones,-4);
  assert(await page.getByLabel('播放聲音').locator('option[value=mix]').evaluate(e=>e.disabled));
  await page.getByLabel('播放聲音').selectOption('source');
  await page.getByRole('button',{name:'播放',exact:true}).click();await page.getByRole('button',{name:'暫停',exact:true}).waitFor();await page.getByRole('button',{name:'暫停',exact:true}).click();
  const result={source:transposed.key_context.source,target:transposed.key_context.target,semitones:-4,guitar_play_pause:true,original_source_play_pause:true,mix_disabled:true,real_revision_writes:0,intercepted_revision_attempts:revisionAttempts};
  await writeFile(new URL('playback-after.json',out),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
