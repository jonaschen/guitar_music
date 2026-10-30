// Run against an isolated trial stack with its own data directory or volume.
// This checks the running application; it does not certify dependency installation.
import {chromium,expect as baseExpect} from '@playwright/test';
const expect=baseExpect.configure({timeout:30000});
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
const base=process.argv[2]||'http://127.0.0.1:5273';
const out=process.argv[3]||'../output/evaluation/friend-trial-2026-10-30';
await mkdir(out,{recursive:true});
const api=base+'/backend';
const credentials=process.env.GUITARSCRIBE_WEB_ACCESS_FILE?JSON.parse(await readFile(process.env.GUITARSCRIBE_WEB_ACCESS_FILE,'utf8')):undefined;
const authHeaders=credentials?{Authorization:'Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64')}:{};
const request=(url,options={})=>fetch(url,{...options,headers:{...authHeaders,...options.headers}});
if(credentials){assert.equal((await fetch(base)).status,401);assert.equal((await fetch(api+'/api/v1/capabilities')).status,401);}

const capabilities=await(await request(api+'/api/v1/capabilities')).json();
assert.equal(capabilities.improved_accompaniment,true);assert.equal(capabilities.youtube_enabled,true);
// Existing host runtimes may retain archived packages; submissions below must still disable melody.
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const errors=[];let savedId;
try{
 const page=await browser.newPage({httpCredentials:credentials,viewport:{width:390,height:844}});page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);
 await page.getByRole('button',{name:'開啟範例：小手拉大手',exact:true}).click();
 await expect(page.getByLabel('和弦時間表',{exact:true}).getByRole('button')).toHaveCount(132);
 assert.equal(await page.getByLabel('播放聲音',{exact:true}).inputValue(),'guitar');
 await page.getByRole('button',{name:'播放',exact:true}).click();
 await expect(page.getByLabel('跟彈提示',{exact:true})).toContainText('目前 F',{timeout:30000});
 await page.getByRole('button',{name:'暫停',exact:true}).click();
 await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
 await page.getByLabel('和弦時間表',{exact:true}).getByRole('button').first().click();
 await page.getByLabel('和弦名稱',{exact:true}).fill('Em');
 const save=page.waitForResponse(r=>r.url().endsWith('/revisions')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
 savedId=(await (await save).json()).revision_id;
 await page.reload();
 await expect(page.getByLabel('和弦時間表',{exact:true}).getByRole('button').first()).toContainText('Em');
 await page.getByRole('button',{name:'用這首歌曲開始分析',exact:true}).click();
 await expect(page.getByLabel('YouTube video URL')).toHaveValue('https://www.youtube.com/watch?v=5wq_uTMW0v8');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:out+'/fresh-home.png',fullPage:true});
}finally{await browser.close()}
assert.deepEqual(errors,[]);
// Real local analysis without a private source; the model cache may already be warm.
const form=new FormData();form.append('audio_file',new Blob([await readFile('../fixtures/audio/test_progression.wav')]),'test_progression.wav');
form.append('rights_confirmed','true');form.append('melody_mode','off');form.append('separate_vocals','false');form.append('chord_complexity','full');
const response=await request(api+'/api/v1/jobs',{method:'POST',body:form});assert.equal(response.status,202);
let job=await response.json();console.log('Submitted isolated-trial smoke',job.id);
const deadline=Date.now()+10*60*1000;
while(!['completed','failed','cancelled'].includes(job.status)&&Date.now()<deadline){
 await new Promise(r=>setTimeout(r,3000));job=await(await request(api+'/api/v1/jobs/'+job.id)).json();console.log(job.status,job.progress);
}
assert.equal(job.status,'completed',JSON.stringify(job));assert.equal(job.score.melody.length,0);assert.ok(job.score.chords.length);
assert.equal(job.score.provenance.chord_engine,'chordino');
const manifest=await(await request(api+'/scores/playback/manifest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(job.score)})).json();assert.ok(manifest.events.some(e=>e.track==='guitar'));assert.ok(!manifest.events.some(e=>e.track==='melody'));
await writeFile(out+'/report.json',JSON.stringify({base,capabilities,example:{chords:132,played:true,editedAndReloaded:true,revision:savedId,sourcePrefill:true},analysis:{job:job.id,status:job.status,timing:job.score.analysis.timing_status,chords:job.score.chords.length,engine:job.score.provenance.chord_engine},errors},null,2));
console.log('Example, editing, source intake and actual analysis passed');
