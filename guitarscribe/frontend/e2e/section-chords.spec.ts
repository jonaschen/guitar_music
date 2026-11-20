import {test,expect,type Page} from '@playwright/test';
import {parseChordPractice,applyChordRange,type ChordPracticeDocument} from '../src/chordPracticeDocument';
const source={job_id:'section-song',fingerprint:'a'.repeat(64),audio_sha256:'b'.repeat(64),duration:12,source_start:42};
const seed:ChordPracticeDocument={schema_version:1,source,segments:[{id:'a',start:0,end:6,original_symbol:'C',symbol:null,status:'pending'},{id:'b',start:6,end:12,original_symbol:'G',symbol:null,status:'pending'}]};
const sections=[{id:'intro',start:0,end:4,label:'intro',display_label:'前奏'},{id:'chorus',start:4,end:10,label:'chorus',display_label:'副歌'},{id:'outro',start:10,end:12,label:'outro',display_label:'尾奏'}].map(s=>({...s,name_review_status:'user_confirmed',boundary_review_status:'user_confirmed',note:'',model_sections:[]}));
const structure={schema_version:1,candidate_sha256:null,source,sections};
test('editing a clipped chord range preserves outside decisions and original evidence',()=>{
 const next=applyChordRange(seed,{start:4,end:10},{start:4,end:8},'Am/C');
 expect(next.segments.map(s=>[s.start,s.end,s.original_symbol,s.symbol])).toEqual([[0,4,'C',null],[4,6,'C','Am/C'],[6,8,'G','Am/C'],[8,12,'G',null]]);
 expect(seed.segments).toHaveLength(2);expect(parseChordPractice(JSON.stringify(next),source)).toEqual(next);
 expect(()=>applyChordRange(seed,{start:4,end:10},{start:3,end:5},'C')).toThrow();
});
test('unknown differs from N.C.; malformed source symbol and overlaps are rejected',()=>{
 const noChord=applyChordRange(seed,{start:4,end:10},{start:4,end:6},'N.C.');expect(noChord.segments[1].status).toBe('confirmed');
 expect(applyChordRange(noChord,{start:4,end:10},{start:4,end:6},null).segments[1].status).toBe('pending');
 expect(()=>applyChordRange(seed,{start:4,end:10},{start:4,end:6},'Hminor')).toThrow();
 expect(()=>parseChordPractice(JSON.stringify(seed),{...source,audio_sha256:'c'.repeat(64)})).toThrow();
 expect(()=>parseChordPractice(JSON.stringify({...seed,segments:[...seed.segments,seed.segments[0]]}))).toThrow();
});
function wav(){const n=8000*12,b=Buffer.alloc(44+n*2);b.write('RIFF');b.writeUInt32LE(36+n*2,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(16000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n*2,40);return b;}
async function setup(page:Page,linked=true){const state={document:structuredClone(seed),version:0,structureVersion:1,writes:[] as any[],otherWrites:[] as string[],fail:false,mismatch:false,saveGate:null as Promise<void>|null};
 await page.route('**/backend/**',async r=>{const path=new URL(r.request().url()).pathname,method=r.request().method();
  if(path.endsWith('/chord-practice')){if(method==='PUT'){const body=r.request().postDataJSON();state.writes.push(body);if(state.fail)return r.abort();if(body.expected_version!==state.version||body.structure_version!==state.structureVersion)return r.fulfill({status:409,json:{detail:'changed'}});state.document=body.document;state.version++;await state.saveGate;}
   return r.fulfill({json:{job_id:source.job_id,document:state.document,version:state.version,current_source:source,source_matches:!state.mismatch}});}
  if(method!=='GET'&&method!=='HEAD')state.otherWrites.push(path);
  if(path.endsWith('/song-structure'))return r.fulfill({json:{job_id:source.job_id,version:state.structureVersion,document:structure,current_source:source,source_matches:!state.mismatch}});
  if(path.endsWith('/root-practice'))return r.fulfill({json:{job_id:source.job_id,version:0,document:{schema_version:1,source:{...source,audio_sha256:undefined},segments:[{id:'root',start:0,end:12,original_root:0,root:null,status:'pending'}]}}});
  if(path.endsWith('/audio')){const body=wav(),m=/bytes=(\d+)-(\d*)/.exec(r.request().headers().range??'');if(m){const start=Number(m[1]),end=m[2]?Number(m[2]):body.length-1;return r.fulfill({status:206,body:body.subarray(start,end+1),contentType:'audio/wav',headers:{'content-range':`bytes ${start}-${end}/${body.length}`}});}return r.fulfill({body,contentType:'audio/wav'});}
  return r.fulfill({status:404,json:{detail:'fixture'}});
 });
 await page.goto('/?practice=chords&job=section-song'+(linked?'&structure=chorus&structure_source='+source.fingerprint+'&section_start=4&section_end=10':''));return state;}
test('locked section crops graph and audio, saves its slice, reopens and undoes',async({page})=>{
 await page.addInitScript(()=>{(window as any).spectrumDurations=[];const post=Worker.prototype.postMessage;Worker.prototype.postMessage=function(data:any,...args:any[]){if(data.channels)(window as any).spectrumDurations.push(data.channels[0].length/data.rate);return (post as any).call(this,data,...args);};});
 const server=await setup(page);await expect(page.getByRole('heading',{name:'已鎖定：副歌',exact:true})).toBeVisible();
 const chart=page.getByRole('slider',{name:'頻譜定位時間',exact:true});await expect(chart).toHaveAttribute('aria-valuemin','4');await expect(chart).toHaveAttribute('aria-valuemax','10');
 await page.getByRole('button',{name:'產生低頻圖',exact:true}).click();await expect(page.getByLabel('頻譜狀態')).toContainText('低頻圖已就緒');expect(await page.evaluate(()=>(window as any).spectrumDurations)).toEqual([6]);await page.getByRole('button',{name:'看整段',exact:true}).click();await expect(chart).toHaveAttribute('aria-valuemin','4');
 await page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();await page.getByLabel('和弦名稱',{exact:true}).fill('Am/C');await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');
 await expect(page.getByLabel('我的和弦時間軸').getByRole('button')).toContainText(['Am/C']);
 expect(server.writes).toHaveLength(1);expect(server.writes[0].section_id).toBe('chorus');expect(server.document.segments[0]).toMatchObject({start:0,end:4,symbol:null});expect(server.document.segments.at(-1)).toMatchObject({end:12,symbol:null});
 await page.getByRole('button',{name:'復原和弦修改',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');expect(server.document.segments.every(s=>s.symbol===null)).toBe(true);
 await page.getByRole('button',{name:'重做和弦修改',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');await page.reload();await expect(page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true})).toContainText('Am/C');expect(server.otherWrites).toEqual([]);
});
test('missing lock is explicit and selecting a section does not write or play',async({page})=>{
 const server=await setup(page,false);await expect(page.getByRole('button',{name:'採用／更新和弦',exact:true})).toHaveCount(0);await page.getByLabel('要練習的歌曲段落',{exact:true}).selectOption('chorus');await page.getByRole('button',{name:'鎖定這段練和弦',exact:true}).click();await expect(page.getByRole('heading',{name:'已鎖定：副歌',exact:true})).toBeVisible();expect(server.writes).toEqual([]);expect(await page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(true);await page.reload();await expect(page.getByRole('heading',{name:'已鎖定：副歌',exact:true})).toBeVisible();
});
test('cold original playback stays inside section and no synth is added',async({page})=>{
 await page.addInitScript(()=>{(window as any).tones=0;OscillatorNode.prototype.start=function(){(window as any).tones++;};});const server=await setup(page);await page.getByRole('button',{name:'播放原曲範圍',exact:true}).click();await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeGreaterThanOrEqual(4);await page.locator('audio').evaluate(a=>{(a as HTMLAudioElement).currentTime=10.05;});await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeLessThan(5);await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));expect(await page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(true);expect(await page.evaluate(()=>(window as any).tones)).toBe(0);expect(server.writes).toEqual([]);
});
test('A-B fill including N.C. and clear preserves outside and refuses out-of-lock edits',async({page})=>{
 const server=await setup(page);await page.getByLabel('和弦開始秒數').fill('5');await page.getByLabel('和弦結束秒數').fill('8');await page.getByRole('button',{name:'標記無和弦 N.C.',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');expect(server.document.segments.filter(s=>s.start>=5&&s.end<=8).every(s=>s.symbol==='N.C.')).toBe(true);
 await page.getByRole('button',{name:'清除為待聽',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');expect(server.document.segments.every(s=>s.symbol===null)).toBe(true);
 await page.getByLabel('和弦開始秒數').fill('3');await page.getByLabel('和弦名稱',{exact:true}).fill('C');await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();await expect(page.getByText('請在鎖定段落內選範圍，和弦可填 C、Am、G7、C/E 或 N.C.。',{exact:true})).toBeVisible();expect(server.writes).toHaveLength(2);
});
test('version conflict retains draft across reload and never overwrites newer progress',async({page})=>{
 const server=await setup(page);await page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();server.version=1;await page.getByLabel('和弦名稱',{exact:true}).fill('Dm');await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();await expect(page.getByRole('alert')).toContainText('版本已變動');await page.reload();await expect(page.getByRole('alert')).toContainText('未保存草稿');expect(server.writes).toHaveLength(1);expect(server.document.segments.every(s=>s.symbol===null)).toBe(true);await expect(page.getByRole('button',{name:'下載未保存和弦',exact:true})).toBeVisible();
});
test('offline saved draft recovers and retries; changed structure blocks applying it',async({page})=>{
 const server=await setup(page);server.fail=true;await page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();await page.getByLabel('和弦名稱',{exact:true}).fill('F');await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();await expect(page.getByRole('alert')).toContainText('連線中斷');server.fail=false;await page.getByRole('button',{name:'重試保存／載入',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');
 server.structureVersion=2;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(page.getByRole('alert')).toContainText('歌曲結構或來源已變動');await expect(page.getByRole('button',{name:'採用／更新和弦',exact:true})).toBeDisabled();expect(server.document.segments.some(s=>s.symbol==='F')).toBe(true);
});
test('stale section links require reselect; narrow view and source mismatch remain safe',async({page})=>{
 const server=await setup(page);await page.goto('/?practice=chords&job=section-song&structure=chorus&structure_source='+source.fingerprint+'&section_start=3&section_end=10');await expect(page.getByLabel('和弦保存狀態')).toContainText('連結的段落已改動');await expect(page.getByRole('button',{name:'採用／更新和弦',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'鎖定這段練和弦',exact:true}).click();await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 server.mismatch=true;await page.reload();await expect(page.getByRole('alert')).toContainText('錄音來源已變動');expect(server.writes).toEqual([]);
});
test('missing browser storage does not prevent source-bound server saving',async({page})=>{
 await page.addInitScript(()=>{Storage.prototype.getItem=function(){throw Error('unavailable');};Storage.prototype.setItem=function(){throw Error('unavailable');};Storage.prototype.removeItem=function(){throw Error('unavailable');};});
 const server=await setup(page);await page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();await page.getByLabel('和弦名稱',{exact:true}).fill('Em7');await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');expect(server.document.segments.some(s=>s.symbol==='Em7')).toBe(true);
});

test('late successful save never hides a structure-change block reason',async({page})=>{
 const server=await setup(page);let release!:()=>void;server.saveGate=new Promise<void>(resolve=>{release=resolve;});
 await page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true}).click();await page.getByLabel('和弦名稱',{exact:true}).fill('Dm7');await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();
 try{await expect.poll(()=>server.version).toBe(1);server.structureVersion++;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await expect(page.getByRole('alert')).toContainText('歌曲結構或來源已變動');}finally{release();}
 await expect(page.getByRole('button',{name:'重試保存／載入',exact:true})).toBeEnabled();await expect(page.getByRole('alert')).toContainText('歌曲結構或來源已變動');await expect(page.getByRole('button',{name:'採用／更新和弦',exact:true})).toBeDisabled();
});

async function reuseSetup(page:Page){
 const server=await setup(page);server.document=applyChordRange(seed,{start:0,end:4},{start:0,end:2},'C');server.version=7;await page.reload();
 const seen={plans:0,applies:0,hold:null as Promise<void>|null,loseResponse:false};
 await page.route('**/chord-practice/reuse-*',async r=>{
  const path=new URL(r.request().url()).pathname;
  if(path.endsWith('/reuse-ledger'))return r.fulfill({json:{job_id:source.job_id,version:server.version,source_matches:true,operations:[]}});
  const body=r.request().postDataJSON();
  if(path.endsWith('/reuse-plan')){seen.plans++;await seen.hold;return r.fulfill({json:{job_id:source.job_id,version:body.expected_version,structure_version:body.structure_version,plan_id:'a'.repeat(64),request:body,can_apply:body.alignment_confirmed,rows:[{id:'b'.repeat(64),start:4,end:6,symbol:'C',status:'fillable'}]}});}
  if(path.endsWith('/reuse-apply')){seen.applies++;server.document=applyChordRange(server.document,{start:4,end:10},{start:4,end:6},'C');server.version++;
   if(seen.loseResponse)return r.abort();return r.fulfill({json:{snapshot:{job_id:source.job_id,version:server.version,document:server.document,current_source:source,source_matches:true},operation:{}}});}
  return r.fulfill({status:404});
 });
 await page.getByText('沿用其他段的和弦',{exact:true}).click();return {server,seen};
}
test('chord reuse requires explicit comparison and changing a range invalidates its plan',async({page})=>{
 const {seen}=await reuseSetup(page);
 await page.getByRole('button',{name:'預覽可沿用和弦',exact:true}).click();
 await expect(page.getByRole('button',{name:'套用勾選和弦',exact:true})).toBeDisabled();
 await page.getByLabel('我已比較兩段原曲，確認核心對齊').check();
 await expect(page.getByLabel('和弦沿用預覽')).toHaveCount(0);
 await page.getByRole('button',{name:'預覽可沿用和弦',exact:true}).click();
 await expect(page.getByRole('button',{name:'套用勾選和弦',exact:true})).toBeEnabled();
 await page.getByLabel('來源核心結束秒數').fill('2');await expect(page.getByLabel('和弦沿用預覽')).toHaveCount(0);
 await expect(page.getByLabel('我已比較兩段原曲，確認核心對齊')).not.toBeChecked();expect(seen.applies).toBe(0);
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('late preview cannot apply after manual editing and saving changes the chord version',async({page})=>{
 const {seen,server}=await reuseSetup(page);let release!:()=>void;seen.hold=new Promise<void>(r=>release=r);
 await page.getByLabel('我已比較兩段原曲，確認核心對齊').check();await page.getByRole('button',{name:'預覽可沿用和弦',exact:true}).click();
 await expect.poll(()=>seen.plans).toBe(1);
 await page.getByLabel('和弦名稱',{exact:true}).fill('Dm');await page.getByRole('button',{name:'採用／更新和弦',exact:true}).click();
 await expect(page.getByLabel('和弦保存狀態')).toHaveText('已保存');release();await expect(page.getByRole('button',{name:'預覽可沿用和弦',exact:true})).toBeEnabled();
 await expect(page.getByLabel('和弦沿用預覽')).toHaveCount(0);expect(server.version).toBe(8);expect(seen.applies).toBe(0);
});
test('lost reuse response blocks repeat apply and recovers the committed snapshot on reload',async({page})=>{
 const {seen,server}=await reuseSetup(page);seen.loseResponse=true;
 await page.getByLabel('我已比較兩段原曲，確認核心對齊').check();await page.getByRole('button',{name:'預覽可沿用和弦',exact:true}).click();
 await page.getByRole('button',{name:'套用勾選和弦',exact:true}).click();await expect(page.getByRole('alert')).toContainText('沿用結果需要重新核對');
 await expect(page.getByRole('button',{name:'採用／更新和弦',exact:true})).toBeDisabled();expect(seen.applies).toBe(1);
 await page.reload();await expect(page.getByRole('button',{name:'編輯和弦 4.000–6.000',exact:true})).toContainText('C');expect(server.version).toBe(8);expect(seen.applies).toBe(1);
});
