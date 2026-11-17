import {test,expect,type Page} from '@playwright/test';
const source={job_id:'phone-song',fingerprint:'a'.repeat(64),audio_sha256:'b'.repeat(64),duration:12,source_start:42};
const structure={schema_version:1,candidate_sha256:null,source,sections:[{id:'intro',start:0,end:4,label:'intro',display_label:'前奏',name_review_status:'user_confirmed',boundary_review_status:'unreviewed',note:'',model_sections:[]},{id:'chorus',start:4,end:12,label:'chorus',display_label:'副歌',name_review_status:'unreviewed',boundary_review_status:'unreviewed',note:'',model_sections:[]}]};
function wav(){const n=8000*12,b=Buffer.alloc(44+n*2);b.write('RIFF');b.writeUInt32LE(36+n*2,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(16000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n*2,40);return b;}
async function fixture(page:Page,candidate=false,mismatch=false,audioGate?:Promise<void>){const requests:string[]=[],mutations:string[]=[];
 await page.route('**/backend/**',async r=>{const path=new URL(r.request().url()).pathname;requests.push(r.request().url());if(!['GET','HEAD'].includes(r.request().method()))mutations.push(path);
 if(path.endsWith('/song-structure'))return r.fulfill({json:{job_id:source.job_id,version:candidate?0:1,document:candidate?null:structure,current_source:source,source_matches:!mismatch}});
 if(path.endsWith('/song-structure/analysis'))return r.fulfill({json:{job_id:source.job_id,state:'ready',candidate:structure}});
 if(path.endsWith('/root-practice'))return r.fulfill({json:{job_id:source.job_id,version:1,document:{schema_version:1,source:{...source,audio_sha256:undefined},segments:[{id:'r1',start:0,end:4,original_root:0,root:0,status:'confirmed'},{id:'r2',start:4,end:12,original_root:7,root:null,status:'pending'}]}}});
 if(path.endsWith('/audio')){await audioGate;const body=wav(),m=/bytes=(\d+)-(\d*)/.exec(r.request().headers().range??'');if(m){const start=Number(m[1]),end=m[2]?Number(m[2]):body.length-1;return r.fulfill({status:206,body:body.subarray(start,end+1),contentType:'audio/wav',headers:{'content-range':`bytes ${start}-${end}/${body.length}`,'accept-ranges':'bytes'}});}return r.fulfill({body,contentType:'audio/wav'});}
 return r.fulfill({status:404,json:{detail:'fixture'}});
 });await page.goto('/?practice=demo&job=phone-song',{waitUntil:'domcontentloaded'});return{requests,mutations};}
test('phone presentation walks structure, local-time original audio and spectrum without any writes or tones',async({page})=>{
 await page.addInitScript(()=>{(window as any).toneCount=0;const start=OscillatorNode.prototype.start;OscillatorNode.prototype.start=function(...args:any[]){(window as any).toneCount++;return(start as any).apply(this,args);};});
 const state=await fixture(page);await expect(page.getByRole('main',{name:'手機介紹'})).toBeVisible();await page.getByRole('button',{name:'介紹第 2 段 副歌',exact:true}).tap();await page.getByRole('button',{name:'下一步：聽這一段',exact:true}).tap();
 await page.getByRole('button',{name:'播放選定段落',exact:true}).tap();await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeGreaterThanOrEqual(4);
 await page.getByRole('button',{name:'下一步：看低頻圖',exact:true}).tap();expect(await page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(true);await page.getByRole('button',{name:'產生低頻圖',exact:true}).tap();await expect(page.getByLabel('頻譜狀態')).toContainText('低頻圖已就緒');
 expect(state.requests.filter(u=>u.includes('/audio?')).every(u=>u.includes('/song-structure/audio?')&&u.includes('audio_sha256='))).toBe(true);
 expect(state.mutations).toEqual([]);expect(await page.evaluate(()=>(window as any).toneCount)).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('ready candidate can be demonstrated without applying or confirming it',async({page})=>{
 const state=await fixture(page,true);await expect(page.getByText('展示的是分析初稿，尚未套用。',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:/套用|確認名稱/})).toHaveCount(0);expect(state.mutations).toEqual([]);
});
test('source mismatch stops demo audio and leaves progress untouched',async({page})=>{
 const state=await fixture(page,false,true);await expect(page.getByRole('alert')).toContainText('來源');expect(state.requests.some(u=>u.includes('/audio?'))).toBe(false);expect(state.mutations).toEqual([]);
});
test('tap starts cold audio before metadata and background/pagehide stop without automatic resume',async({page})=>{
 let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
 await page.addInitScript(()=>{(window as any).playStates=[];const original=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){(window as any).playStates.push(this.readyState);return original.call(this);};});
 await fixture(page,false,false,gate);
 await page.getByRole('button',{name:'介紹第 2 段 副歌',exact:true}).tap();
 await page.getByRole('button',{name:'下一步：聽這一段',exact:true}).tap();
 try{await page.getByRole('button',{name:'播放選定段落',exact:true}).tap();await expect.poll(()=>page.evaluate(()=>(window as any).playStates)).toEqual([0]);}finally{release();}
 await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeGreaterThanOrEqual(4);
 await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));});
 await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(true);
 await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'));});
 expect(await page.evaluate(()=>(window as any).playStates.length)).toBe(1);
 await page.getByRole('button',{name:'播放選定段落',exact:true}).tap();await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));
 expect(await page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(true);
});
test('selected section changes stop audio; explicit A–B loop returns to start',async({page})=>{
 const state=await fixture(page);await page.getByRole('button',{name:'下一步：聽這一段',exact:true}).tap();
 await page.getByRole('button',{name:'播放選定段落',exact:true}).tap();await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(false);
 await page.getByLabel('介紹段落',{exact:true}).selectOption('intro');expect(await page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(true);
 await page.getByRole('checkbox',{name:'A–B 循環',exact:true}).check();await page.getByRole('button',{name:'播放選定段落',exact:true}).tap();
 await page.locator('audio').evaluate(a=>{(a as HTMLAudioElement).currentTime=4.02;});
 await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).currentTime)).toBeLessThan(1);
 expect(await page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(false);
 await page.getByRole('checkbox',{name:'A–B 循環',exact:true}).uncheck();await page.locator('audio').evaluate(a=>{(a as HTMLAudioElement).currentTime=4.02;});
 await expect.poll(()=>page.locator('audio').evaluate(a=>(a as HTMLAudioElement).paused)).toBe(true);expect(state.mutations).toEqual([]);
});
test('narrow and landscape touch layouts preserve route after reload and allow two-tap A–B',async({page})=>{
 const state=await fixture(page);await page.reload();await expect(page).toHaveURL(/practice=demo&job=phone-song/);
 for(const size of [{width:360,height:780},{width:844,height:390}]){await page.setViewportSize(size);await page.getByRole('button',{name:'3. 看低頻',exact:true}).tap();
 const slider=page.getByRole('slider',{name:'頻譜定位時間',exact:true});await slider.tap({position:{x:45,y:50}});await page.getByRole('button',{name:'游標設為 A（開始）',exact:true}).tap();await slider.tap({position:{x:120,y:50}});await page.getByRole('button',{name:'游標設為 B（結束）',exact:true}).tap();
 expect(await page.getByLabel('A 開始時間').textContent()).not.toBe(await page.getByLabel('B 結束時間').textContent());expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
 expect(state.mutations).toEqual([]);
});
