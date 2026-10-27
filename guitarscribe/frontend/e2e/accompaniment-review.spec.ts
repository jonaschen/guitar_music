import { test, expect, type Route } from '@playwright/test';

const score = {
  schema_version:'1.0', song:{title:'Entry preview test',source_type:'local',duration_seconds:8},
  analysis:{key:'C',mode:'major',bpm:120,time_signature:'4/4',capo:0,confidence:1,warnings:[]},
  key_context:{source:{key:'C',mode:'major'},target:{key:'C',mode:'major'},shape:{key:'C',mode:'major'},sounding:{key:'C',mode:'major'},transpose_semitones:0,accidental_preference:'auto',audio_matches_notation:true},
  guitar:{tuning:[40,45,50,55,59,64],tuning_name:'EADGBE',capo:0,max_capo:8,max_fret:15,handedness:'right',difficulty:'beginner',tab_preference:'balanced'},
  beats:Array.from({length:16},(_,i)=>({time:i*.5,beat:i%4+1,measure:Math.floor(i/4)+1,confidence:1})),
  chords:[{id:'c',start:0,end:8,symbol:'C',confidence:1,origin:'model',edited:false,voicing_id:null,available_voicings:[]}],
  melody:[],rhythm:{subdivision:8,pattern_id:'',display:['D',null,'D','U'],confidence:1,label:'test'},
  provenance:{beat_engine:'test',chord_engine:'test',melody_engine:'test',parameters:{}},
};
const manifest = {revision:'test',duration_seconds:8,bpm:120,time_signature:'4/4',events:[
  {id:'g',track:'guitar',start:0,end:8,sustain_end:8,pitches:[48],pitch_offsets:[0],pitch_velocities:[98],velocity:98,source_id:'c'},
]};
const preview={candidate:manifest,changes:[{chord_id:'c'}],skipped:[]};


function wavFile() {
  const frames=8*8000;const b=Buffer.alloc(44+frames*2);
  b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(16000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(frames*2,40);
  for(let i=0;i<frames;i++)b.writeInt16LE(Math.round(3000*Math.sin(i*2*Math.PI*220/8000)),44+i*2);
  return b;
}
async function setup(page:any,workingScore:any=score,holdAudio=false){
  await page.addInitScript(()=>{
    localStorage.setItem('guitarscribe.workspaceMode','focus');
    const w=window as any;w.__sources=[];w.__oscillators=0;
    const Native=window.AudioContext;let contextId=0;
    w.AudioContext=class extends Native {
      id=++contextId;
      createBufferSource(){const n=super.createBufferSource();const start=n.start.bind(n),stop=n.stop.bind(n);const record:any={context:this.id,stops:[]};w.__sources.push(record);
        n.start=(when=0,offset=0,duration?:number)=>{Object.assign(record,{when,offset,duration,bufferDuration:n.buffer?.duration,rate:n.playbackRate.value});start(when,offset,duration);};
        n.stop=(when?:number)=>{record.stops.push(when??-1);stop(when);};return n;}
      createOscillator(){w.__oscillators++;return super.createOscillator();}
    };
  });
  await page.route('**/api/v1/capabilities', (r:Route)=>r.fulfill({json:{melody_available:true}}));
  await page.route('**/api/v1/jobs/entry-job',(r:Route)=>r.fulfill({json:{id:'entry-job',status:'completed',progress:100,artifacts:[],score:workingScore}}));
  await page.route('**/rhythm-patterns?*',(r:Route)=>r.fulfill({json:[]}));
  await page.route('**/scores/playback/manifest',(r:Route)=>r.fulfill({json:{...manifest,events:[...manifest.events,{id:'melody',track:'melody',start:0,end:8,pitches:[72],velocity:96}]}}));
  if(!holdAudio)await page.route('**/api/v1/jobs/entry-job/audio',(r:Route)=>r.fulfill({contentType:'audio/wav',body:wavFile()}));
  await page.goto('/?job=entry-job');
}

test('mix uses one audio clock, no melody, loops and resumes without source offset drift',async({page})=>{
  await setup(page);const panel=page.getByRole('region',{name:'和弦核對'});
  await page.getByLabel('核對小節數').selectOption('2');
  await panel.getByRole('checkbox',{name:'循環這一段'}).check();
  await panel.getByRole('button',{name:'從這段開頭播放'}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.bufferDuration===8).length)).toBeGreaterThan(0);
  const first=await page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.when!==undefined));
  const original=first.find((s:any)=>s.bufferDuration===8);const guitar=first.find((s:any)=>s.bufferDuration!==8);
  expect(original.context).toBe(guitar.context);expect(original.when).toBeCloseTo(guitar.when,6);expect(original.offset).toBe(0);expect(original.duration).toBe(4);expect(original.rate).toBe(1);
  expect(await page.evaluate(()=>(window as any).__oscillators)).toBe(0);
  await expect.poll(()=>page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.bufferDuration===8).length),{timeout:8000}).toBeGreaterThan(1);
  const loops=await page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.bufferDuration===8));
  expect(loops[1].when-loops[0].when).toBeCloseTo(4,6);expect(loops[1].offset).toBe(0);
  await panel.getByRole('button',{name:'暫停核對'}).click();
  await expect(panel.getByRole('button',{name:'續播這段核對'})).toBeEnabled();
  await panel.getByRole('button',{name:'續播這段核對'}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.bufferDuration===8).length)).toBeGreaterThan(loops.length);
  const resumed=await page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.bufferDuration===8).at(-1));
  expect(resumed.offset).toBeGreaterThan(0);expect(resumed.offset+resumed.duration).toBeCloseTo(4,5);
  await panel.getByRole('button',{name:'暫停核對'}).click();
});

test('source and guitar modes are separate, changing selection stops playback',async({page})=>{
  await setup(page);const panel=page.getByRole('region',{name:'和弦核對'});
  await panel.getByRole('button',{name:'只聽原曲',exact:true}).click();
  await panel.getByRole('button',{name:'從這段開頭播放'}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.when!==undefined).length)).toBe(1);
  expect(await page.evaluate(()=>(window as any).__sources.find((s:any)=>s.when!==undefined).bufferDuration)).toBe(8);
  await panel.getByRole('button',{name:'只聽吉他',exact:true}).click();
  expect(await page.evaluate(()=>(window as any).__sources.find((s:any)=>s.when!==undefined).stops.includes(-1))).toBe(true);
  await panel.getByRole('button',{name:'從這段開頭播放'}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.when!==undefined).length)).toBeGreaterThan(1);
  expect(await page.evaluate(()=>(window as any).__sources.filter((s:any)=>s.bufferDuration===8).length)).toBe(1);
  await page.getByLabel('核對起始小節').selectOption('1');
  await expect(panel.getByRole('button',{name:'暫停核對'})).toBeDisabled();
});

test('cancelled audio fetch cannot start later and transposed mixes are disabled',async({page})=>{
  const held:Route[]=[];await page.route('**/api/v1/jobs/entry-job/audio',r=>{held.push(r);});
  await setup(page,score,true);const panel=page.getByRole('region',{name:'和弦核對'});
  await panel.getByRole('button',{name:'從這段開頭播放'}).click();
  await expect(panel.getByRole('button',{name:'取消準備'})).toBeEnabled();
  await panel.getByRole('button',{name:'取消準備'}).click();
  for(const route of held)await route.fulfill({contentType:'audio/wav',body:wavFile()});
  await expect(panel.getByRole('button',{name:'從這段開頭播放'})).toBeEnabled();
  expect(await page.evaluate(()=>(window as any).__sources.length)).toBe(0);
  const shifted=structuredClone(score);shifted.key_context.audio_matches_notation=false;
  await page.route('**/api/v1/jobs/entry-job',r=>r.fulfill({json:{id:'entry-job',status:'completed',progress:100,artifacts:[],score:shifted}}));
  await page.reload();await expect(panel.getByRole('button',{name:'從這段開頭播放'})).toBeDisabled();
  await expect(panel.getByText(/工作譜已移調/)).toBeVisible();
  await panel.getByRole('button',{name:'只聽吉他',exact:true}).click();
  await expect(panel.getByRole('button',{name:'從這段開頭播放'})).toBeEnabled();
});

test('simple accompaniment view preserves melody tools and exposes nearby settings',async({page})=>{
  await setup(page);
  await page.goto('/?job=entry-job&view=accompaniment');
  const panel=page.getByRole('region',{name:'和弦核對'});
  await expect(panel).toBeVisible();
  await expect(page.getByLabel('Tab start bar')).toBeHidden();
  await panel.getByRole('button',{name:'伴奏設定與拍長整理'}).click();
  await expect(page.getByLabel('吉他演奏方案')).toBeVisible();
  await page.getByLabel('吉他演奏方案').selectOption('continuous');
  await page.getByRole('button',{name:'回到和弦核對',exact:true}).click();
  await expect(panel.getByText('吉他演奏：換和弦即彈・連續刷奏')).toBeVisible();
  await page.getByRole('button',{name:'旋律編輯（實驗）',exact:true}).click();
  await expect(page.getByLabel('Tab start bar')).toBeVisible();
  await page.getByRole('button',{name:'簡潔和弦頁',exact:true}).click();
  await expect(page.getByLabel('Tab start bar')).toBeHidden();
  await page.setViewportSize({width:390,height:844});
  expect(await panel.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
});


test('new users land on accepted chord view and explicit melody selection survives reload',async({page})=>{
  await setup(page);
  await page.evaluate(()=>{localStorage.removeItem('guitarscribe.editorView');localStorage.removeItem('guitarscribe.workspaceMode');});
  await page.reload();
  await expect(page.getByRole('region',{name:'和弦核對'})).toBeVisible();
  await expect(page.getByLabel('Tab start bar')).toBeHidden();
  await page.getByRole('button',{name:'旋律編輯（實驗）',exact:true}).click();
  await expect(page.getByLabel('Tab start bar')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Tab start bar')).toBeVisible();
  await page.getByRole('button',{name:'簡潔和弦頁',exact:true}).click();
  await page.reload();
  await expect(page.getByLabel('Tab start bar')).toBeHidden();
  await expect(page.getByRole('region',{name:'和弦核對'})).toBeVisible();
});
