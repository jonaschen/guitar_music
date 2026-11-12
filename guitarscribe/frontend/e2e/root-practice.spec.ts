import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {rootClock} from '../src/rootPracticeAudio';
import {parseRootDocument,splitRootSegment,mergeRootSegment} from '../src/rootPracticeDocument';
const fixture=JSON.parse(readFileSync(new URL('./fixtures/accepted-chord-grid.json',import.meta.url),'utf8'));
const source={job_id:'root-job',fingerprint:'a'.repeat(64),duration:8,source_start:0};
const seed={schema_version:1 as const,source,segments:[{id:'a',start:0,end:4,original_root:0,root:null,status:'pending' as const},{id:'b',start:4,end:8,original_root:7,root:null,status:'pending' as const}]};
function wav(){const count=8000*8,buffer=Buffer.alloc(44+count*2);buffer.write('RIFF');buffer.writeUInt32LE(36+count*2,4);buffer.write('WAVEfmt ',8);buffer.writeUInt32LE(16,16);buffer.writeUInt16LE(1,20);buffer.writeUInt16LE(1,22);buffer.writeUInt32LE(8000,24);buffer.writeUInt32LE(16000,28);buffer.writeUInt16LE(2,32);buffer.writeUInt16LE(16,34);buffer.write('data',36);buffer.writeUInt32LE(count*2,40);for(let i=0;i<count;i++)buffer.writeInt16LE(Math.round(Math.sin(i/8000*220*Math.PI*2)*2000),44+2*i);return buffer;}
async function setup(page:Page){
  page.on('pageerror',error=>console.error('ROOT PAGE ERROR',error.message));
  const server={version:0,document:structuredClone(seed) as any,writes:0,scoreWrites:0,conflict:false,fail:false};
  const score={...fixture,provenance:{...fixture.provenance,parameters:{}},song:{...fixture.song,title:'根音練習測試',duration_seconds:8,source_start_seconds:0},chords:[{...fixture.chords[0],id:'a',start:0,end:4,symbol:'C'},{...fixture.chords[0],id:'b',start:4,end:8,symbol:'G'}],melody:[]};
  score.key_context={source:{key:'C',mode:'major'},target:{key:'C',mode:'major'},shape:{key:'C',mode:'major'},sounding:{key:'C',mode:'major'},transpose_semitones:0,accidental_preference:'auto',audio_matches_notation:true};
  score.guitar={tuning:[40,45,50,55,59,64],tuning_name:'EADGBE',capo:0,max_capo:8,max_fret:15,handedness:'right',difficulty:'beginner',tab_preference:'balanced'};
  score.rhythm={subdivision:8,pattern_id:'',display:['D',null,'D','U'],confidence:1,label:'test'};
  score.schema_version='1.0';
  await page.route('**/api/v1/capabilities',r=>r.fulfill({json:{melody_available:false,youtube_enabled:true}}));
  await page.route('**/api/v1/jobs/root-job',r=>r.fulfill({json:{id:'root-job',status:'completed',score,artifacts:['source']}}));
  await page.route('**/rhythm-patterns?*',r=>r.fulfill({json:[]}));
  await page.route('**/revisions',r=>{server.scoreWrites++;return r.fulfill({json:{revision_id:'unexpected'}});});
  await page.route('**/api/v1/jobs/root-job/root-practice',r=>{
    if(r.request().method()==='PUT'){
      const body=r.request().postDataJSON();if(server.fail)return r.abort();
      if(server.conflict||body.expected_version!==server.version)return r.fulfill({status:409,json:{detail:'conflict'}});
      server.document=body.document;server.version++;server.writes++;
    }
    return r.fulfill({json:{job_id:'root-job',version:server.version,document:server.document,updated_at:null}});
  });
  await page.route('**/api/v1/jobs/root-job/root-candidates',r=>r.fulfill({json:{state:'ready',message:'已準備'}}));
  await page.route('**/api/v1/jobs/root-job/root-candidates/rank',r=>{const body=r.request().postDataJSON();return r.fulfill({json:{...body,status:'available',coverage:1,candidates:[{pitch_class:0,name:'C',rank:1,score:.3},{pitch_class:4,name:'E',rank:2,score:.2},{pitch_class:7,name:'G',rank:3,score:.1}]}});});
  await page.route('**/api/v1/jobs/root-job/root-practice/audio?*',r=>r.fulfill({body:wav(),contentType:'audio/wav'}));
  await page.goto('/?job=root-job&practice=roots');
  try{await expect(page.getByRole('main',{name:'根音抓歌練習'})).toBeVisible({timeout:20000});}catch(error){console.error('ROOT BODY',await page.locator('body').innerText());throw error;}
  await expect(page.locator('.root-candidates button')).toHaveCount(3);
  return server;
}

test('document and clock preserve source time, uncertainty and split/merge semantics',()=>{
  const d=parseRootDocument(JSON.stringify(seed));
  const split=splitRootSegment(d,'a',2);expect(split.segments).toHaveLength(3);expect(mergeRootSegment(split,'a').segments).toHaveLength(2);
  expect(()=>parseRootDocument(JSON.stringify({...d,source:{...source,fingerprint:'b'.repeat(64)}}),source)).toThrow();
  expect(()=>splitRootSegment(d,'a',0)).toThrow();
  expect(rootClock(6,1,5,2,true)).toBe(4);expect(rootClock(20,1,5,2,false)).toBe(5);expect(rootClock(-1,1,5,2,false)).toBe(2);
});

test('audition never writes, adoption saves, reopen and unsure/undo/redo preserve the original score',async({page})=>{
  const server=await setup(page);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await page.locator('.root-candidates button').nth(1).click();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'暫停',exact:true}).click();await page.waitForTimeout(650);expect(server.writes).toBe(0);
  await page.getByRole('button',{name:'採用這個根音',exact:true}).click();await expect.poll(()=>server.version).toBe(1);expect(server.document.segments[0].root).toBe(4);
  await expect(page.getByLabel('根音保存狀態')).toHaveText('已保存');
  await page.reload();await expect(page.locator('.root-current')).toContainText('E · 已採用');
  await page.getByRole('button',{name:'還聽不出來',exact:true}).click();await expect.poll(()=>server.version).toBe(2);
  await page.getByRole('button',{name:'復原',exact:true}).click();await expect.poll(()=>server.document.segments[0].root).toBe(4);
  await page.getByRole('button',{name:'重做',exact:true}).click();await expect.poll(()=>server.document.segments[0].status).toBe('unsure');
  expect(server.scoreWrites).toBe(0);expect(errors).toEqual([]);
});

test('manual twelve notes, split/merge, backup restore and sequential decisions work',async({page})=>{
  const server=await setup(page);
  await page.getByText('其他音（十二音）',{exact:true}).click();await page.getByRole('button',{name:'試聽 Bb',exact:true}).click();await page.getByRole('button',{name:'採用這個根音',exact:true}).click();await expect.poll(()=>server.document.segments[0].root).toBe(10);
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  await page.getByLabel('根音練習播放位置').evaluate((el:HTMLInputElement)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(el,'2');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));});
  await page.getByText('段落調整',{exact:true}).click();await page.getByRole('button',{name:'從游標處分成兩段'}).click();await expect.poll(()=>server.document.segments.length).toBe(3);
  expect(server.document.segments[0].status).toBe('pending');expect(server.document.segments[0].end).toBe(2);
  await page.getByRole('button',{name:'與下一段合併'}).click();await expect.poll(()=>server.document.segments.length).toBe(2);
  await page.getByRole('button',{name:'下一段',exact:true}).click();await expect(page.locator('.root-segment-heading h2')).toContainText('第 2 段');
  await page.getByText('進度與備份',{exact:true}).click();
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'下載完整練習'}).click();expect((await download).suggestedFilename()).toBe('root-practice-root-job.json');
  const restored=structuredClone(seed) as any;restored.segments[1].root=2;restored.segments[1].status='confirmed';
  await page.getByLabel('還原根音備份').setInputFiles({name:'roots.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(restored))});await expect.poll(()=>server.document.segments[1].root,{timeout:15000}).toBe(2);
  await page.getByRole('button',{name:'連聽我的行進'}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();expect(server.scoreWrites).toBe(0);
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  await page.getByLabel('根音練習播放位置').evaluate((el:HTMLInputElement)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(el,'6');el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));});
  await expect(page.getByLabel('根音練習播放位置')).toHaveValue('6');await page.getByRole('button',{name:'播放行進',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  expect(Number(await page.getByLabel('根音練習播放位置').inputValue())).toBeGreaterThanOrEqual(6);
});

test('expired analysis keeps the saved practice reachable, exportable and usable for root-only audition',async({page})=>{
  const server=await setup(page);
  server.version=1;server.document.segments[0].root=4;server.document.segments[0].status='confirmed';
  await page.route('**/api/v1/jobs/root-job',r=>r.fulfill({status:404,json:{detail:'expired'}}));
  await page.route('**/api/v1/jobs/root-job/root-candidates',r=>r.fulfill({status:404,json:{detail:'expired'}}));
  await page.route('**/api/v1/jobs/root-job/root-practice/audio?*',r=>r.fulfill({status:404,json:{detail:'expired'}}));
  await page.reload();
  await expect(page.getByRole('heading',{name:'已保存的根音練習',exact:true})).toBeVisible();
  await expect(page.locator('.root-current')).toContainText('E · 已採用');
  expect(new URL(page.url()).searchParams.get('job')).toBe('root-job');
  await page.getByLabel('根音練習聲音').selectOption('root');
  await page.getByRole('button',{name:'播放這段',exact:true}).click();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  await page.getByText('進度與備份',{exact:true}).click();
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'下載完整練習'}).click();
  expect((await download).suggestedFilename()).toBe('root-practice-root-job.json');
  expect(server.writes).toBe(0);
});

test('conflict keeps the local draft and requires explicit reload instead of overwriting',async({page})=>{
  const server=await setup(page);server.conflict=true;
  await page.locator('.root-candidates button').first().click();await page.getByRole('button',{name:'採用這個根音'}).click();
  await expect(page.getByLabel('根音保存狀態')).toContainText('另一分頁');expect(server.writes).toBe(0);
  const raw=await page.evaluate(()=>sessionStorage.getItem('guitarscribe.root-practice.v1.root-job'));expect(JSON.parse(raw!).document.segments[0].root).toBe(0);
  await expect(page.getByRole('button',{name:'採用這個根音'})).toBeDisabled();
  server.conflict=false;page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'載入最新版本',exact:true}).click();
  await expect(page.getByLabel('根音保存狀態')).toHaveText('尚未採用任何根音');expect(server.document.segments[0].root).toBeNull();
});

test('offline edits recover after reload and retry without losing the decision',async({page})=>{
  const server=await setup(page);server.fail=true;
  await page.getByRole('button',{name:'還聽不出來'}).click();await expect(page.getByLabel('根音保存狀態')).toContainText('連線中斷');
  server.fail=false;await page.reload();await expect(page.getByRole('main',{name:'根音抓歌練習'})).toBeVisible({timeout:20000});await expect.poll(()=>server.document.segments[0].status,{timeout:15000}).toBe('unsure');await expect(page.getByLabel('根音保存狀態')).toHaveText('已保存');
});

test('late candidate response never replaces a newer segment and missing clues allow manual work',async({page})=>{
  await setup(page);let release!:()=>void;const held=new Promise<void>(resolve=>release=resolve);
  await page.route('**/root-candidates/rank',async r=>{const body=r.request().postDataJSON();if(body.start===0)await held;await r.fulfill({json:{...body,status:'insufficient',candidates:[]}}).catch(()=>{});});
  await page.getByRole('button',{name:'下一段',exact:true}).click();await expect(page.locator('.root-candidates button')).toHaveCount(0);
  await page.getByRole('button',{name:'上一段',exact:true}).click();await page.getByRole('button',{name:'下一段',exact:true}).click();release();
  await expect(page.locator('.root-segment-heading h2')).toContainText('第 2 段');await expect(page.getByRole('button',{name:'試聽 F',exact:true})).toBeVisible();
});

test('real WebAudio uses the chosen pitch, aligned source clock, and cancels old voices',async({page})=>{
  await page.addInitScript(()=>{
    const records:Array<any>=[];(window as any).__rootAudio=records;
    const start=AudioBufferSourceNode.prototype.start,stop=AudioBufferSourceNode.prototype.stop;
    const ids=new WeakMap<AudioBufferSourceNode,number>();let next=0;
    AudioBufferSourceNode.prototype.start=function(...args:Parameters<AudioBufferSourceNode['start']>){
      const id=++next;ids.set(this,id);let pitch:number|null=null;
      if(this.buffer&&Math.abs(this.buffer.duration-4)<.01){
        const data=this.buffer.getChannelData(0),sr=this.buffer.sampleRate;let best=-1;
        for(let p=0;p<12;p++){const hz=440*2**((48+p-69)/12);let real=0,imag=0;for(let i=0;i<6000;i++){const phase=2*Math.PI*hz*i/sr;real+=data[i]*Math.cos(phase);imag+=data[i]*Math.sin(phase);}const energy=real*real+imag*imag;if(energy>best){best=energy;pitch=p;}}
      }
      records.push({kind:'start',id,when:args[0],duration:this.buffer?.duration,pitch});return start.apply(this,args);
    };
    AudioBufferSourceNode.prototype.stop=function(...args:Parameters<AudioBufferSourceNode['stop']>){records.push({kind:'stop',id:ids.get(this),when:args[0]??0});return stop.apply(this,args);};
  });
  const server=await setup(page);await page.locator('.root-candidates button').nth(1).click();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  let records=await page.evaluate(()=>(window as any).__rootAudio);
  const sourceStart=records.find((r:any)=>r.kind==='start'&&r.duration===8),noteStart=records.find((r:any)=>r.kind==='start'&&r.pitch===4);
  expect(sourceStart).toBeTruthy();expect(noteStart).toBeTruthy();expect(Math.abs(sourceStart.when-noteStart.when)).toBeLessThan(.01);
  await page.locator('.root-candidates button').nth(2).click();await page.waitForTimeout(250);
  await page.getByRole('button',{name:'暫停',exact:true}).click();records=await page.evaluate(()=>(window as any).__rootAudio);
  expect(records.some((r:any)=>r.kind==='start'&&r.pitch===7)).toBe(true);
  for(const r of records.filter((r:any)=>r.kind==='start'))expect(records.some((s:any)=>s.kind==='stop'&&s.id===r.id)).toBe(true);
  expect(server.writes).toBe(0);
});

for(const width of [320,390,768,1440])test(`complete practice interface fits ${width}px and uses visible keyboard focus`,async({page})=>{
  await page.setViewportSize({width,height:844});await setup(page);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const panel=page.locator('.root-clues');await panel.scrollIntoViewIfNeeded();
  const first=await page.locator('.root-candidates button').first().boundingBox(),adopt=await page.getByRole('button',{name:'採用這個根音'}).boundingBox();
  expect(adopt!.y+adopt!.height-first!.y).toBeLessThan(650);
  expect(first!.height).toBeGreaterThanOrEqual(44);
  await page.locator('.root-candidates button').first().focus();await expect(page.locator('.root-candidates button').first()).toBeFocused();
  await page.screenshot({path:`test-results/root-practice-${width}.png`,fullPage:true});
  await page.getByLabel('先自己聽，隱藏參考音').check();await expect(page.locator('.root-candidates')).toHaveCount(0);await expect(page.getByRole('button',{name:'試聽 C',exact:true})).toBeVisible();
});
