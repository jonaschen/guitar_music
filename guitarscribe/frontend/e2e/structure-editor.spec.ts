import {test,expect,type Page} from '@playwright/test';
import {parseStructure,renameSection,moveBoundary,splitSection,mergeSection,confirmSection,type StructureDocument} from '../src/songStructureDocument';
const source={job_id:'structure-job',fingerprint:'a'.repeat(64),audio_sha256:'b'.repeat(64),duration:12,source_start:42};
const seed:StructureDocument={schema_version:1,source,candidate_sha256:'c'.repeat(64),sections:[
  {id:'a',start:0,end:4,label:'intro',display_label:'前奏',name_review_status:'user_confirmed',boundary_review_status:'user_confirmed',model_sections:[{id:'m1',start:0,end:4,label:'intro',model_end:4,original_number:1}],note:''},
  {id:'b',start:4,end:8,label:'verse',display_label:'主歌',name_review_status:'user_confirmed',boundary_review_status:'user_confirmed',model_sections:[{id:'m2',start:4,end:8,label:'verse',model_end:8,original_number:2}],note:''},
  {id:'c',start:8,end:12,label:'chorus',display_label:'副歌',name_review_status:'unreviewed',boundary_review_status:'unreviewed',model_sections:[],note:''}]};

test('boundary change invalidates both neighbors only and preserves model evidence',()=>{
 const result=moveBoundary(seed,'b',5);
 expect(result.sections.map(s=>[s.start,s.end,s.boundary_review_status])).toEqual([[0,5,'unreviewed'],[5,8,'unreviewed'],[8,12,'unreviewed']]);
 expect(result.sections[0].name_review_status).toBe('user_confirmed');
 expect(result.sections[0].model_sections).toEqual(seed.sections[0].model_sections);
 expect(seed.sections[0].end).toBe(4);
 expect(()=>moveBoundary(seed,'b',8)).toThrow();
});
test('split merge retain model provenance and reset confirmation of new sections',()=>{
 const split=splitSection(seed,'b',6);expect(split.sections).toHaveLength(4);
 expect(new Set(split.sections.map(s=>s.id)).size).toBe(4);
 expect(split.sections.slice(1,3).map(s=>s.name_review_status)).toEqual(['unreviewed','unreviewed']);
 const merged=mergeSection(split,split.sections[1].id);expect(merged.sections).toHaveLength(3);
 expect(merged.sections[1].model_sections).toHaveLength(1);
 expect(merged.sections[1].boundary_review_status).toBe('unreviewed');
 expect(()=>splitSection(seed,'a',0)).toThrow();
});
test('closing custom label and name confirmation never confirm boundaries',()=>{
 const changed=renameSection(seed,'b','closing','收尾段（較接近主歌）');
 expect(changed.sections[1].label).toBe('closing');expect(changed.sections[1].name_review_status).toBe('user_corrected');
 const result=confirmSection(changed,'c','name');
 expect(result.sections[2].name_review_status).toBe('user_confirmed');expect(result.sections[2].boundary_review_status).toBe('unreviewed');
});
test('backup rejects other sources gaps overlap unknown fields and invalid time',()=>{
 expect(parseStructure(JSON.stringify(seed),source)).toEqual(seed);
 for(const alter of [(d:any)=>d.source.audio_sha256='d'.repeat(64),(d:any)=>d.sections[1].start=5,(d:any)=>d.sections[1].end=9,(d:any)=>d.sections[0].id='b',(d:any)=>d.root=[]]){
   const doc=structuredClone(seed);alter(doc);expect(()=>parseStructure(JSON.stringify(doc),source)).toThrow();
 }
});

function wav(){const n=8000*12,b=Buffer.alloc(44+n*2);b.write('RIFF');b.writeUInt32LE(36+n*2,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(16000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n*2,40);return b;}
async function setup(page:Page,empty=false){
 const state={document:empty?null:structuredClone(seed),version:empty?0:1,writes:0,otherWrites:0,fail:false,readFail:false,sourceMatches:true,conflict:false,history:[] as any[]};
 await page.route('**/backend/**',async route=>{
  const r=route.request(),url=new URL(r.url());
  if(url.pathname.endsWith('/song-structure')){
   if(r.method()==='GET'&&state.readFail)return route.abort();
   if(r.method()==='PUT'){if(state.fail)return route.abort();const body=r.postDataJSON();if(state.conflict||body.expected_version!==state.version)return route.fulfill({status:409});if(state.document)state.history.unshift({version:state.version,document:structuredClone(state.document),updated_at:null});state.document=body.document;state.version++;state.writes++;}
   return route.fulfill({json:{job_id:source.job_id,version:state.version,document:state.document,updated_at:null,current_source:source,source_matches:state.sourceMatches,source_error:null}});
  }
  if(url.pathname.endsWith('/song-structure/history'))return route.fulfill({json:state.history});
  if(url.pathname.endsWith('/song-structure/audio')){const body=wav(),m=/bytes=(\d+)-(\d*)/.exec(r.headers().range??'');if(m){const start=Number(m[1]),end=m[2]?Number(m[2]):body.length-1;return route.fulfill({status:206,body:body.subarray(start,end+1),contentType:'audio/wav',headers:{'content-range':`bytes ${start}-${end}/${body.length}`,'accept-ranges':'bytes'}});}return route.fulfill({body,contentType:'audio/wav'});}
  if(!['GET','HEAD'].includes(r.method()))state.otherWrites++;
  if(url.pathname.endsWith('/capabilities'))return route.fulfill({json:{melody_available:false,youtube_enabled:true}});
  return route.fulfill({status:404,json:{detail:'fixture'}});
 });
 await page.goto('/?job=structure-job&practice=structure');
 await expect(page.getByRole('main',{name:'歌曲結構編輯'})).toBeVisible();return state;
}
test('editing saves, reloads and can undo without any root or score writes',async({page})=>{
 const server=await setup(page);await page.getByRole('button',{name:'選取第 2 段 主歌',exact:true}).click();
 await page.getByLabel('段落類別').selectOption('chorus');await page.getByRole('button',{name:'套用名稱',exact:true}).click();
 await expect.poll(()=>server.document!.sections[1].label).toBe('chorus');
 await page.getByRole('button',{name:'復原',exact:true}).click();await expect.poll(()=>server.document!.sections[1].label).toBe('verse');
 await page.getByRole('button',{name:'重做',exact:true}).click();await expect.poll(()=>server.document!.sections[1].label).toBe('chorus');
 await page.reload();await expect(page.getByRole('button',{name:'選取第 2 段 副歌',exact:true})).toBeVisible();expect(server.otherWrites).toBe(0);
});
test('boundary split merge and confirmations keep a complete reversible document',async({page})=>{
 const server=await setup(page);await page.getByRole('button',{name:'選取第 2 段 主歌',exact:true}).click();
 await page.getByLabel('段落開始秒數').fill('5');await page.getByRole('button',{name:'套用開始交界'}).click();
 await expect.poll(()=>server.document!.sections[1].start).toBe(5);expect(server.document!.sections[0].boundary_review_status).toBe('unreviewed');
 await page.getByLabel('分開位置秒數').fill('6');await page.getByRole('button',{name:'在此分開'}).click();await expect.poll(()=>server.document!.sections.length).toBe(4);
 await page.getByRole('button',{name:'與下一段合併'}).click();await expect.poll(()=>server.document!.sections.length).toBe(3);
 await page.getByRole('button',{name:'確認名稱',exact:true}).click();await expect.poll(()=>server.document!.sections[1].name_review_status).toBe('user_confirmed');
 expect(server.document!.sections[1].boundary_review_status).toBe('unreviewed');expect(server.otherWrites).toBe(0);
});
test('offline retry and competing version keep drafts and never overwrite silently',async({page})=>{
 const server=await setup(page);server.fail=true;await page.getByLabel('段落名稱').fill('前奏修改');await page.getByRole('button',{name:'套用名稱'}).click();
 await expect(page.getByLabel('結構保存狀態')).toContainText('連線中斷');expect(server.writes).toBe(0);
 expect(await page.evaluate(()=>sessionStorage.getItem('guitarscribe.structure.draft.v1.structure-job'))).toContain('前奏修改');
 server.fail=false;await page.getByRole('button',{name:'重試保存／載入'}).click();await expect.poll(()=>server.writes).toBe(1);
 server.conflict=true;await page.getByLabel('段落名稱').fill('衝突草稿');await page.getByRole('button',{name:'套用名稱'}).click();
 await expect(page.getByLabel('結構保存狀態')).toContainText('版本或來源已變動');expect(server.writes).toBe(1);
});
test('source audition uses local time and practice link carries scope without writing',async({page})=>{
 const server=await setup(page);await page.getByRole('button',{name:'選取第 2 段 主歌',exact:true}).click();
 await page.getByRole('button',{name:'聽這段',exact:true}).click();await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeGreaterThanOrEqual(4);
 await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused),{timeout:10000,intervals:[100]}).toBe(true);
 expect(await page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeLessThan(8.5);
 const link=page.getByRole('link',{name:'練這段根音',exact:true});await expect(link).toHaveAttribute('href',/section_start=4/);await expect(link).toHaveAttribute('href',/structure_source=aaaa/);expect(server.writes).toBe(0);
});
test('new songs can start an explicitly manual unknown structure',async({page})=>{
 const server=await setup(page,true);await page.getByRole('button',{name:'建立手動結構'}).click();await expect.poll(()=>server.document?.sections.length).toBe(1);expect(server.document!.sections[0].label).toBe('unknown');expect(server.document!.candidate_sha256).toBeNull();
});
for(const width of [390,768,1440])test(`structure editor fits ${width}px`,async({page})=>{await page.setViewportSize({width,height:1000});await setup(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);});


test('offline reload retries loading current source and version before saving retained draft',async({page})=>{
 const server=await setup(page);server.fail=true;
 await page.getByLabel('段落名稱').fill('離線前奏');await page.getByRole('button',{name:'套用名稱'}).click();
 await expect(page.getByLabel('結構保存狀態')).toContainText('連線中斷');
 server.readFail=true;await page.reload();await expect(page.getByLabel('結構保存狀態')).toContainText('載入');
 server.readFail=false;server.fail=false;await page.getByRole('button',{name:'重試保存／載入'}).click();
 await expect.poll(()=>server.document!.sections[0].display_label).toBe('離線前奏');
 await expect(page.getByLabel('結構保存狀態')).toHaveText('已保存');
});

test('saving one tab never clears another tab draft',async({page,context})=>{
 await setup(page);const other=await context.newPage();
 await other.goto('/');await other.evaluate(()=>sessionStorage.setItem('guitarscribe.structure.draft.v1.structure-job','other tab draft'));
 await page.getByLabel('段落名稱').fill('本頁前奏');await page.getByRole('button',{name:'套用名稱'}).click();
 await expect(page.getByLabel('結構保存狀態')).toHaveText('已保存');
 expect(await other.evaluate(()=>sessionStorage.getItem('guitarscribe.structure.draft.v1.structure-job'))).toBe('other tab draft');await other.close();
});


test('source mismatch disables and unloads audition while preserving export',async({page})=>{
 const server=await setup(page);server.sourceMatches=false;await page.reload();
 await expect(page.getByRole('button',{name:'聽這段',exact:true})).toBeDisabled();
 await expect(page.locator('audio')).not.toHaveAttribute('src',/audio/);
 await expect(page.getByRole('button',{name:'下載結構備份'})).toBeEnabled();
});
test('unapplied fields cannot confirm the previous saved name or boundaries',async({page})=>{
 await setup(page);await page.getByLabel('段落名稱').fill('尚未套用');
 await expect(page.getByRole('button',{name:'確認名稱',exact:true})).toBeDisabled();
 await page.getByLabel('段落結束秒數').fill('3');
 await expect(page.getByRole('button',{name:'確認這段邊界'})).toBeDisabled();
});
test('rescue draft wrapper can be previewed and imported with current server version',async({page})=>{
 const server=await setup(page);const restored=structuredClone(seed);restored.sections[0].display_label='救援前奏';
 await page.getByText('備份與歷次保存',{exact:true}).click();
 await page.getByLabel('匯入結構備份').setInputFiles({name:'draft.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({version:999,document:restored}))});
 expect(server.writes).toBe(0);await page.getByRole('button',{name:'套用預覽'}).click();
 await expect.poll(()=>server.document!.sections[0].display_label).toBe('救援前奏');expect(server.version).toBe(2);
});

test('invalid draft stays blocked and intact after retry until explicit discard',async({page})=>{
 const server=await setup(page);await page.evaluate(()=>sessionStorage.setItem('guitarscribe.structure.draft.v1.structure-job','invalid raw backup'));
 await page.reload();await expect(page.getByLabel('結構保存狀態')).toContainText('格式不符');
 await page.getByRole('button',{name:'重試保存／載入'}).click();await expect(page.getByLabel('結構保存狀態')).toContainText('格式不符');
 await expect(page.getByRole('button',{name:'套用名稱'})).toBeDisabled();
 expect(await page.evaluate(()=>sessionStorage.getItem('guitarscribe.structure.draft.v1.structure-job'))).toBe('invalid raw backup');expect(server.writes).toBe(0);
});

test('structure workspace provides a readable light surface over the application theme',async({page})=>{
 await setup(page);expect(await page.getByRole('main',{name:'歌曲結構編輯'}).evaluate(e=>getComputedStyle(e).backgroundColor)).toBe('rgb(243, 246, 247)');
});
test('native playback interruption does not report a failed recording',async({page})=>{
 await setup(page);await page.locator('audio').evaluate(a=>{a.play=()=>Promise.reject(new DOMException('Playback interrupted by pause','AbortError'));});
 await page.getByRole('button',{name:'聽這段',exact:true}).click();
 await expect(page.getByText('原曲暫時無法播放，請確認連線後再試。',{exact:true})).not.toBeVisible();
});

test('long section lists scroll without shrinking names and timestamps over neighboring rows',async({page})=>{
 const server=await setup(page);server.document!.sections=Array.from({length:20},(_,i)=>({...structuredClone(seed.sections[0]),id:`row-${i}`,start:i*.6,end:(i+1)*.6,display_label:'收尾段（較接近主歌）'}));
 await page.setViewportSize({width:390,height:800});await page.reload();
 const first=page.getByRole('navigation',{name:'歌曲段落清單'}).getByRole('button').first();
 await expect(first).toBeVisible();expect(await first.evaluate(b=>b.querySelector('small')!.getBoundingClientRect().bottom<=b.getBoundingClientRect().bottom)).toBe(true);
});
