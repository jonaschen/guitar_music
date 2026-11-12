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
  await page.getByRole('button',{name:'參考音 E2',exact:true}).click();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'暫停',exact:true}).click();await page.waitForTimeout(650);expect(server.writes).toBe(0);
  await page.getByRole('button',{name:'採用這個根音',exact:true}).click();await expect.poll(()=>server.version).toBe(1);expect(server.document.segments[0].root).toBe(4);
  await expect(page.getByLabel('根音保存狀態')).toHaveText('已保存');
  await page.reload();await expect(page.locator('.root-current')).toContainText('E2 · 已採用');
  await page.getByRole('button',{name:'還聽不出來',exact:true}).click();await expect.poll(()=>server.version).toBe(2);
  await page.getByRole('button',{name:'復原',exact:true}).click();await expect.poll(()=>server.document.segments[0].root).toBe(4);
  await page.getByRole('button',{name:'重做',exact:true}).click();await expect.poll(()=>server.document.segments[0].status).toBe('unsure');
  expect(server.scoreWrites).toBe(0);expect(errors).toEqual([]);
});

test('manual twelve notes, split/merge, backup restore and sequential decisions work',async({page})=>{
  const server=await setup(page);
  await page.getByText('其他音（Eb2–Eb3）',{exact:true}).click();await page.getByRole('button',{name:'試聽 Bb2',exact:true}).click();await page.getByRole('button',{name:'採用這個根音',exact:true}).click();await expect.poll(()=>server.document.segments[0].root).toBe(10);
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
  await expect(page.locator('.root-current')).toContainText('E2 · 已採用');
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
  await page.getByRole('button',{name:'參考音 C3',exact:true}).click();await page.getByRole('button',{name:'採用這個根音'}).click();
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
  await expect(page.locator('.root-segment-heading h2')).toContainText('第 2 段');await expect(page.getByRole('button',{name:'試聽 F2',exact:true})).toBeVisible();
});

test('real audio holds low E across source loops, steps across B/C and cancels old tones',async({page})=>{
  await page.addInitScript(()=>{
    const records:Array<any>=[];(window as any).__rootAudio=records;
    const scheduled=new WeakMap<AudioParam,number>(),setValue=AudioParam.prototype.setValueAtTime;
    AudioParam.prototype.setValueAtTime=function(value:number,time:number){scheduled.set(this,value);return setValue.call(this,value,time);};
    let next=0;
    for(const [kind,prototype] of [['tone',OscillatorNode.prototype],['source',AudioBufferSourceNode.prototype]] as const){
      const start=prototype.start,stop=prototype.stop,ids=new WeakMap<any,number>();
      prototype.start=function(...args:any[]){
        const id=++next;ids.set(this,id);records.push({kind,id,event:'start',when:args[0],hz:scheduled.get((this as OscillatorNode).frequency)});
        return (start as any).apply(this,args);
      };
      prototype.stop=function(...args:any[]){records.push({kind,id:ids.get(this),event:'stop',when:args[0]??0});return (stop as any).apply(this,args);};
    }
  });
  const server=await setup(page);
  await expect(page.locator('.root-candidates strong')).toHaveText(['E2','G2','C3']);
  await page.getByRole('button',{name:'參考音 E2',exact:true}).click();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  await page.waitForTimeout(5100); // Source loop is 4.75 seconds; held tone must not retrigger.
  let records=await page.evaluate(()=>(window as any).__rootAudio);
  const tones=records.filter((r:any)=>r.kind==='tone'&&r.event==='start');
  expect(tones).toHaveLength(1);expect(tones[0].hz).toBeCloseTo(82.4069,3);
  const source=records.find((r:any)=>r.kind==='source'&&r.event==='start');
  expect(Math.abs(source.when-tones[0].when)).toBeLessThan(.001);
  expect(records.filter((r:any)=>r.event==='stop')).toHaveLength(0);
  await page.getByRole('button',{name:'低半音',exact:true}).click();
  await expect(page.locator('.root-current')).toContainText('Eb2');
  await expect(page.getByRole('button',{name:'低半音',exact:true})).toBeDisabled();
  records=await page.evaluate(()=>(window as any).__rootAudio);
  expect(records.filter((r:any)=>r.kind==='tone'&&r.event==='start').at(-1).hz).toBeCloseTo(77.7817,3);
  await page.getByRole('button',{name:'高半音',exact:true}).click();await expect(page.locator('.root-current')).toContainText('E2');
  await page.getByText('其他音（Eb2–Eb3）',{exact:true}).click();
  await expect(page.locator('.root-pitch-grid button')).toHaveText(['Eb2','E2','F2','Gb2','G2','Ab2','A2','Bb2','B2','C3','Db3','D3','Eb3']);
  await page.getByRole('button',{name:'試聽 B2',exact:true}).click();
  await page.getByRole('button',{name:'高半音',exact:true}).click();
  await expect(page.locator('.root-current')).toContainText('C3');
  records=await page.evaluate(()=>(window as any).__rootAudio);
  expect(records.filter((r:any)=>r.kind==='tone'&&r.event==='start').at(-1).hz).toBeCloseTo(130.8128,3);
  await page.getByRole('button',{name:'低半音',exact:true}).click();await expect(page.locator('.root-current')).toContainText('B2');
  await page.getByRole('button',{name:'試聽 Eb3',exact:true}).click();await expect(page.getByRole('button',{name:'高半音',exact:true})).toBeDisabled();
  records=await page.evaluate(()=>(window as any).__rootAudio);
  expect(records.filter((r:any)=>r.kind==='tone'&&r.event==='start').at(-1).hz).toBeCloseTo(155.5635,3);
  await page.getByRole('button',{name:'試聽 Eb2',exact:true}).click();
  await expect(page.getByRole('button',{name:'試聽 Eb2',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(page.getByRole('button',{name:'試聽 Eb3',exact:true})).toHaveAttribute('aria-pressed','false');
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  records=await page.evaluate(()=>(window as any).__rootAudio);
  for(const r of records.filter((r:any)=>r.event==='start'))expect(records.some((s:any)=>s.event==='stop'&&s.id===r.id&&s.kind===r.kind)).toBe(true);
  expect(server.writes).toBe(0);
  await page.getByRole('button',{name:'採用這個根音',exact:true}).click();await expect.poll(()=>server.document.segments[0].root).toBe(3);
});

test('rendered root tones have actual Eb2-Eb3 fundamentals and steady late audio with silence at the segment end',async({page})=>{
  await setup(page);
  const results=await page.evaluate(async()=>{
    const modulePath='/src/rootPracticeTone.ts';const {createRootTone}=await import(modulePath);
    const results=[];
    for(let midi=39;midi<=51;midi++){
      const context=new OfflineAudioContext(1,44100*3,44100);
      createRootTone(context,midi%12,0,context.destination,2.5,midi);
      const data=(await context.startRendering()).getChannelData(0);
      let best=0,detected=0;
      for(let note=28;note<=64;note++){
        const hz=440*2**((note-69)/12);let re=0,im=0;
        for(let i=0;i<12000;i++){const phase=2*Math.PI*hz*i/44100;re+=data[i+44100]*Math.cos(phase);im+=data[i+44100]*Math.sin(phase);}
        const power=re*re+im*im;if(power>best){best=power;detected=note;}
      }
      const rms=(seconds:number)=>{let sum=0;const start=Math.round(seconds*44100);for(let i=start;i<start+4410;i++)sum+=data[i]**2;return Math.sqrt(sum/4410);};
      results.push({midi,detected,early:rms(.2),late:rms(2.2),after:rms(2.7)});
    }
    return results;
  });
  for(const r of results){expect(r.detected).toBe(r.midi);expect(r.late).toBeGreaterThan(.05);expect(r.late/r.early).toBeGreaterThan(.95);expect(r.late/r.early).toBeLessThan(1.05);expect(r.after).toBe(0);}
});

async function captureRangeAudio(page:Page){
  await page.addInitScript(()=>{
    const records:any[]=[];(window as any).__rangeAudio=records;
    const values=new WeakMap<AudioParam,number>(),setValue=AudioParam.prototype.setValueAtTime;
    AudioParam.prototype.setValueAtTime=function(value:number,time:number){values.set(this,value);return setValue.call(this,value,time);};
    let next=0;
    for(const [kind,prototype]of [['tone',OscillatorNode.prototype],['source',AudioBufferSourceNode.prototype]]as const){
      const start=prototype.start,stop=prototype.stop,ids=new WeakMap<any,number>();
      prototype.start=function(...args:any[]){const id=++next;ids.set(this,id);const source=this as AudioBufferSourceNode;
        records.push({kind,id,event:'start',at:args[0],offset:args[1],duration:args[2],hz:values.get((this as OscillatorNode).frequency),loop:source.loop,loopStart:source.loopStart,loopEnd:source.loopEnd});return(start as any).apply(this,args);};
      prototype.stop=function(...args:any[]){records.push({kind,id:ids.get(this),event:'stop',at:args[0]??this.context.currentTime});return(stop as any).apply(this,args);};
    }
  });
}

test('selected range loops known roots with source-only gaps, clips boundaries and resumes in an unknown segment',async({page})=>{
  await captureRangeAudio(page);const server=await setup(page);
  server.version=1;server.document.segments=[
    {id:'a',start:0,end:2,original_root:4,root:4,status:'confirmed'},
    {id:'b',start:2,end:5,original_root:0,root:null,status:'pending'},
    {id:'c',start:5,end:8,original_root:7,root:7,status:'confirmed'}];
  await page.reload();await expect(page.locator('.root-progression button')).toHaveCount(3);
  // A trial C is deliberately different from the adopted E; range playback must ignore it.
  await page.getByRole('button',{name:'參考音 C3',exact:true}).click();await page.getByRole('button',{name:'暫停',exact:true}).click();
  await page.evaluate(()=>{(window as any).__rangeAudio.length=0;});

  await page.getByLabel('連聽起點秒數').fill('1');await page.getByLabel('連聽終點秒數').fill('3');
  await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();await expect(page.getByRole('button',{name:'暫停範圍',exact:true})).toBeVisible();
  await page.waitForTimeout(4250);
  let records=await page.evaluate(()=>(window as any).__rangeAudio);
  const source=records.find((r:any)=>r.kind==='source'&&r.event==='start'),tones=records.filter((r:any)=>r.kind==='tone'&&r.event==='start');
  expect(source.loop).toBe(true);expect(source.loopStart).toBe(1);expect(source.loopEnd).toBe(3);expect(source.offset).toBe(1);
  expect(records.filter((r:any)=>r.kind==='source'&&r.event==='start')).toHaveLength(1);
  expect(tones.length).toBeGreaterThanOrEqual(3);
  for(const [i,tone]of tones.entries()){
    expect(tone.hz).toBeCloseTo(82.4069,3);expect(tone.at-source.at).toBeCloseTo(i*2,2);
    const stop=records.find((r:any)=>r.kind==='tone'&&r.event==='stop'&&r.id===tone.id);expect(stop.at-tone.at).toBeCloseTo(1.001,2);
  }
  await page.getByRole('button',{name:'暫停範圍',exact:true}).click();
  await page.getByLabel('連聽終點秒數').fill('6');await page.getByLabel('循環選取範圍').uncheck();
  await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();await page.waitForTimeout(1350);
  await page.getByRole('button',{name:'暫停範圍',exact:true}).click();
  const paused=Number(await page.getByLabel('根音練習播放位置').inputValue());expect(paused).toBeGreaterThan(2);expect(paused).toBeLessThan(5);
  await page.evaluate(()=>{(window as any).__rangeAudio.length=0;});
  await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__rangeAudio.filter((r:any)=>r.kind==='tone'&&r.event==='start').length),{timeout:6000}).toBe(1);
  records=await page.evaluate(()=>(window as any).__rangeAudio);
  const resumed=records.find((r:any)=>r.kind==='source'&&r.event==='start'),g=records.find((r:any)=>r.kind==='tone'&&r.event==='start');
  expect(resumed.loop).toBe(false);expect(resumed.offset).toBeCloseTo(paused,2);expect(resumed.duration).toBeCloseTo(6-paused,2);
  expect(g.hz).toBeCloseTo(97.9989,3);expect(g.at-resumed.at).toBeCloseTo(5-paused,2);
  expect(records.find((r:any)=>r.kind==='tone'&&r.event==='stop'&&r.id===g.id).at-g.at).toBeCloseTo(1.001,2);
  await expect(page.getByRole('button',{name:'播放範圍',exact:true})).toBeVisible({timeout:5000});
  expect(server.writes).toBe(0);expect(server.scoreWrites).toBe(0);
  await page.reload();
  await expect(page.getByLabel('連聽起點秒數')).toHaveValue('1');await expect(page.getByLabel('連聽終點秒數')).toHaveValue('6');await expect(page.getByLabel('循環選取範圍')).not.toBeChecked();
});

test('range selection works without any adopted root and rejects invalid or empty bounds',async({page})=>{
  await captureRangeAudio(page);const server=await setup(page);
  await page.getByText('按段落選起終點',{exact:true}).click();await page.getByRole('button',{name:'下一段',exact:true}).click();await page.getByRole('button',{name:'設這段為起點',exact:true}).click();
  await expect(page.getByLabel('連聽起始段')).toHaveValue('b');
  await page.getByLabel('連聽結束段').selectOption('a');await expect(page.getByLabel('連聽起始段')).toHaveValue('a');
  await page.getByLabel('循環選取範圍').uncheck();await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();
  await expect(page.getByRole('button',{name:'暫停範圍',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  const records=await page.evaluate(()=>(window as any).__rangeAudio);
  const source=records.find((r:any)=>r.kind==='source'&&r.event==='start');expect(source.offset).toBe(0);expect(source.duration).toBe(4);
  expect(records.filter((r:any)=>r.kind==='tone')).toHaveLength(0);
  await page.getByLabel('連聽起點秒數').fill('7');
  await expect(page.getByRole('button',{name:'播放選取範圍',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'播放範圍',exact:true})).toBeDisabled();
  await expect(page.getByRole('alert')).toContainText('起點須早於終點');
  await page.getByLabel('連聽起點秒數').fill('');await expect(page.getByRole('button',{name:'播放選取範圍',exact:true})).toBeDisabled();
  await page.getByLabel('連聽起點秒數').fill('0');await page.getByLabel('連聽終點秒數').fill('9');await expect(page.getByRole('button',{name:'播放選取範圍',exact:true})).toBeDisabled();
  expect(server.writes).toBe(0);
});

test('visible A/B sliders select arbitrary boundaries and live markers preserve uninterrupted source playback',async({page})=>{
  await captureRangeAudio(page);const server=await setup(page);
  const start=page.getByLabel('連聽起點秒數'),end=page.getByLabel('連聽終點秒數');
  await expect(start).toBeVisible();await expect(end).toBeVisible();
  const drag=async(label:string,value:string)=>page.getByLabel(label).evaluate((el:HTMLInputElement,v)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},value);
  await drag('拖曳範圍起點','1.25');await drag('拖曳範圍終點','2.75');
  await expect(start).toHaveValue('1.25');await expect(end).toHaveValue('2.75');
  await page.getByLabel('拖曳範圍起點').focus();await page.keyboard.press('ArrowRight');await expect(start).toHaveValue('1.26');
  await drag('拖曳範圍起點','4');expect(Number(await start.inputValue())).toBeCloseTo(2.67,2);
  await drag('拖曳範圍起點','0');await drag('拖曳範圍終點','1');
  await page.getByRole('button',{name:'聽原曲找起終點',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  await expect.poll(async()=>Number(await page.getByLabel('根音練習播放位置').inputValue())).toBeGreaterThan(1.1);
  await page.getByRole('button',{name:'目前位置設為起點',exact:true}).click();const markedStart=Number(await start.inputValue());
  expect(markedStart).toBeGreaterThan(1);await expect(end).toHaveValue('8'); // A beyond old B begins a fresh range.
  await page.waitForTimeout(500);await page.getByRole('button',{name:'目前位置設為終點',exact:true}).click();
  const markedEnd=Number(await end.inputValue());expect(markedEnd-markedStart).toBeGreaterThan(.3);
  await expect(page.getByRole('button',{name:'暫停原曲定位',exact:true})).toBeVisible();
  let records=await page.evaluate(()=>(window as any).__rangeAudio);
  expect(records.filter((r:any)=>r.kind==='source'&&r.event==='start')).toHaveLength(1);expect(records.filter((r:any)=>r.event==='stop'||r.kind==='tone')).toHaveLength(0);
  await page.getByRole('button',{name:'暫停原曲定位',exact:true}).click();
  await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();await expect(page.getByRole('button',{name:'暫停範圍',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  records=await page.evaluate(()=>(window as any).__rangeAudio);const source=records.filter((r:any)=>r.kind==='source'&&r.event==='start').at(-1);
  expect(source.offset).toBeCloseTo(markedStart,2);expect(source.loopStart).toBeCloseTo(markedStart,2);expect(source.loopEnd).toBeCloseTo(markedEnd,2);
  expect(server.writes).toBe(0);
});

for(const width of [320,390,768,1440])test(`complete practice interface fits ${width}px and uses visible keyboard focus`,async({page})=>{
  await page.setViewportSize({width,height:844});await setup(page);
  await expect(page.getByLabel('拖曳範圍起點')).toBeVisible();await expect(page.getByLabel('拖曳範圍終點')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const panel=page.locator('.root-clues');await panel.scrollIntoViewIfNeeded();
  const first=await page.locator('.root-candidates button').first().boundingBox(),adopt=await page.getByRole('button',{name:'採用這個根音'}).boundingBox();
  expect(adopt!.y+adopt!.height-first!.y).toBeLessThan(650);
  expect(first!.height).toBeGreaterThanOrEqual(44);
  await page.locator('.root-candidates button').first().focus();await expect(page.locator('.root-candidates button').first()).toBeFocused();
  await page.screenshot({path:`test-results/root-practice-${width}.png`,fullPage:true});
  await page.getByLabel('先自己聽，隱藏參考音').check();await expect(page.locator('.root-candidates')).toHaveCount(0);await expect(page.getByRole('button',{name:'試聽 C3',exact:true})).toBeVisible();
});

test('manual bar grid derives 115 BPM lengths, shifts both directions and clips song edges',async()=>{
  const {rootBarAt,rootBarLength,rootNearbyBars,rootGridBeats,validRootGrid}=await import('../src/rootPracticeGrid');
  const grid={bpm:115,beats:4,anchor:120.123};
  expect(rootBarLength(grid)).toBeCloseTo(2.086956521739,10);
  const here=rootBarAt(grid,120.2,300),before=rootBarAt(grid,118.1,300);
  expect(here.start).toBeCloseTo(120.123,10);expect(before.end).toBeCloseTo(120.123,10);
  expect(rootBarAt({...grid,anchor:120.133},120.2,300).start-here.start).toBeCloseTo(.01,10);
  expect(rootNearbyBars(grid,50,300)).toHaveLength(5);
  const first=rootBarAt(grid,0,300),last=rootBarAt(grid,300,300);expect(first.start).toBe(0);expect(first.partial).toBe(true);expect(last.end).toBe(300);expect(last.partial).toBe(true);
  const beats=rootGridBeats(grid,120.123,120.123+240/115);expect(beats).toHaveLength(4);expect(beats.map(b=>b.strong)).toEqual([true,false,false,false]);
  expect(rootGridBeats(grid,120.123-240/115,120.123)).toHaveLength(4);
  expect(rootBarLength({...grid,beats:3})).toBeCloseTo(180/115,10);
  expect(validRootGrid({...grid,bpm:0},300)).toBe(false);expect(validRootGrid({...grid,beats:2.5},300)).toBe(false);expect(validRootGrid({...grid,anchor:301},300)).toBe(false);
});

async function setSlider(page:Page,label:string,value:string){
  await page.getByLabel(label,{exact:true}).evaluate((el:HTMLInputElement,value)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},value);
}

test('bar controls align anywhere, select a bar, persist per source and leave adopted roots intact',async({page})=>{
  const server=await setup(page);server.document.segments[0].root=4;server.document.segments[0].status='confirmed';server.version=1;await page.reload();
  await expect(page.getByLabel('節拍器 BPM',{exact:true})).toHaveValue('115');await expect(page.getByLabel('小節長度',{exact:true})).toContainText('每小節 2.087 秒');
  await setSlider(page,'小節對齊全曲定位','5.5');await page.getByRole('button',{name:'目前位置設為小節起點',exact:true}).click();
  await expect(page.getByLabel('小節對齊點秒數')).toHaveValue('5.5');
  await page.getByRole('button',{name:'延後 10 ms',exact:true}).click();await expect(page.getByLabel('小節對齊點秒數')).toHaveValue('5.51');
  await page.getByRole('button',{name:'提前 10 ms',exact:true}).click();await expect(page.getByLabel('小節對齊點秒數')).toHaveValue('5.5');
  // This anchor is late in the source; bars must still exist earlier than it.
  await page.getByRole('button',{name:'選取第 2 小節',exact:true}).click();
  expect(Number(await page.getByLabel('連聽起點秒數').inputValue())).toBeCloseTo(5.5-2*240/115,9);
  expect(Number(await page.getByLabel('連聽終點秒數').inputValue())).toBeCloseTo(5.5-240/115,9);
  await page.getByLabel('每小節幾拍',{exact:true}).fill('3');await expect(page.getByLabel('小節長度',{exact:true})).toContainText('1.565 秒');
  await page.getByLabel('節拍器 BPM',{exact:true}).fill('120');await page.reload();
  await expect(page.getByLabel('節拍器 BPM',{exact:true})).toHaveValue('120');await expect(page.getByLabel('每小節幾拍',{exact:true})).toHaveValue('3');await expect(page.getByLabel('小節對齊點秒數')).toHaveValue('5.5');
  await page.getByLabel('節拍器 BPM',{exact:true}).fill('');await expect(page.getByRole('navigation',{name:'附近小節'})).toHaveCount(0);
  await expect(page.getByRole('alert')).toContainText('BPM');await page.getByLabel('節拍器 BPM',{exact:true}).fill('115');
  expect(server.writes).toBe(0);expect(server.scoreWrites).toBe(0);expect(server.document.segments[0].root).toBe(4);
  await page.evaluate(()=>localStorage.setItem('guitarscribe.root-grid.'+'b'.repeat(64),JSON.stringify({bpm:90,beats:2,anchor:1,click:false})));
  server.document.source={...source,fingerprint:'b'.repeat(64)};await page.reload();await expect(page.getByLabel('節拍器 BPM',{exact:true})).toHaveValue('90');await expect(page.getByLabel('小節對齊點秒數')).toHaveValue('1');
});

test('metronome shares source clock across arbitrary range loops and resumes without a false downbeat',async({page})=>{
  await captureRangeAudio(page);const server=await setup(page);
  await page.getByLabel('節拍器 BPM',{exact:true}).fill('120');await page.getByLabel('小節對齊點秒數').fill('.25');await page.getByLabel('播放時加入節拍聲',{exact:true}).check();
  await page.getByLabel('連聽起點秒數').fill('.1');await page.getByLabel('連聽終點秒數').fill('1.6');
  await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();await page.waitForTimeout(3300);
  let records=await page.evaluate(()=>(window as any).__rangeAudio);
  const sources=records.filter((r:any)=>r.kind==='source'&&r.event==='start'),clicks=records.filter((r:any)=>r.kind==='tone'&&r.event==='start');
  expect(sources).toHaveLength(1);expect(clicks.length).toBeGreaterThanOrEqual(6);
  for(const [i,click] of clicks.entries()){
    expect(click.at-sources[0].at).toBeCloseTo(.15+i*.5,3);expect(click.hz).toBe(i%3===0?1400:900);
  }
  await page.getByRole('button',{name:'暫停範圍',exact:true}).click();
  await setSlider(page,'根音練習播放位置','.4');await page.evaluate(()=>{(window as any).__rangeAudio.length=0;});
  await page.getByLabel('循環選取範圍').uncheck();await setSlider(page,'根音練習播放位置','.4');
  await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();await page.waitForTimeout(600);
  records=await page.evaluate(()=>(window as any).__rangeAudio);
  const resumed=records.find((r:any)=>r.kind==='source'&&r.event==='start'),first=records.find((r:any)=>r.kind==='tone'&&r.event==='start');
  expect(resumed.offset).toBeCloseTo(.4,9);expect(first.hz).toBe(900);expect(first.at-resumed.at).toBeCloseTo(.35,3);
  await page.getByRole('button',{name:'暫停範圍',exact:true}).click();expect(server.writes).toBe(0);
});

test('live metronome realignment and disable do not interrupt source playback',async({page})=>{
  await captureRangeAudio(page);const server=await setup(page);
  await page.getByLabel('播放時加入節拍聲',{exact:true}).check();await page.getByRole('button',{name:'播放原曲對拍',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  await page.waitForTimeout(700);await page.getByRole('button',{name:'目前位置設為小節起點',exact:true}).click();
  const anchor=Number(await page.getByLabel('小節對齊點秒數').inputValue());expect(anchor).toBeGreaterThan(.5);
  await page.waitForTimeout(700);await page.getByLabel('播放時加入節拍聲',{exact:true}).uncheck();
  let records=await page.evaluate(()=>(window as any).__rangeAudio);expect(records.filter((r:any)=>r.kind==='source'&&r.event==='start')).toHaveLength(1);expect(records.filter((r:any)=>r.kind==='source'&&r.event==='stop')).toHaveLength(0);
  const count=records.filter((r:any)=>r.kind==='tone'&&r.event==='start').length;expect(count).toBeGreaterThan(1);await page.waitForTimeout(600);
  records=await page.evaluate(()=>(window as any).__rangeAudio);expect(records.filter((r:any)=>r.kind==='tone'&&r.event==='start')).toHaveLength(count);
  await page.getByRole('button',{name:'暫停對拍',exact:true}).click();expect(server.writes).toBe(0);expect(server.scoreWrites).toBe(0);
});
