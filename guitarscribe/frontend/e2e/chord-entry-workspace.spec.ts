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

test.beforeEach(async ({page})=>{
  await page.route('**/api/v1/capabilities',r=>r.fulfill({json:{youtube_enabled:true,vocal_separation_enabled:true,improved_accompaniment:false,melody_available:true,beat_engine:'test',chord_engine:'test'}}));
  await page.route('**/api/v1/jobs/entry-job',r=>r.fulfill({json:{id:'entry-job',status:'completed',progress:100,artifacts:[],score}}));
  await page.route('**/rhythm-patterns?*',r=>r.fulfill({json:[]}));
  await page.route('**/scores/playback/manifest',r=>r.fulfill({json:manifest}));
  await page.route('**/scores/midi',r=>r.fulfill({contentType:'audio/midi',body:'original-midi'}));
  await page.goto('/?job=entry-job');
  await page.getByText('Compiled score playback',{exact:true}).click();
});

test('explicit mode drives playback and MIDI, restores original and does not persist',async({page})=>{
  const bodies:any[]=[];
  await page.route('**/scores/chord-entry-performance',r=>{
    const body=r.request().postDataJSON();bodies.push(body);
    return body.output==='midi'?r.fulfill({contentType:'audio/midi',body:'candidate-midi'}):r.fulfill({json:preview});
  });
  const select=page.getByLabel('吉他演奏方案');
  await expect(select).toHaveValue('original');
  await select.selectOption('continuous');
  await page.getByRole('button',{name:'Play score',exact:true}).click();
  await expect(page.getByRole('button',{name:'Pause score',exact:true})).toBeVisible();
  await expect(page.getByText(/本次處理 1 段和弦/)).toBeVisible();
  await page.getByRole('button',{name:'Stop score',exact:true}).click();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download MIDI',exact:true}).click();
  expect((await download).suggestedFilename()).toBe('guitarscribe-continuous.mid');
  expect(bodies.map(b=>[b.mode,b.output])).toEqual([['continuous','preview'],['continuous','midi']]);
  expect(bodies[0].score).toEqual({...score,provenance:{...score.provenance,parameters:{analysis_source_job_id:'entry-job'}}});
  await page.getByRole('button',{name:'回原版演奏',exact:true}).click();
  await expect(select).toHaveValue('original');
  const original=page.waitForRequest('**/scores/playback/manifest');
  await page.getByRole('button',{name:'Play score',exact:true}).click();await original;
  await select.selectOption('sparse');
  await expect(page.getByRole('button',{name:'Play score',exact:true})).toBeVisible();
  await page.reload();await page.getByText('Compiled score playback',{exact:true}).click();
  await expect(select).toHaveValue('original');
});

test('late preview cannot start after switching mode',async({page})=>{
  let held:Route|undefined;
  await page.route('**/scores/chord-entry-performance',r=>{held=r;});
  await page.getByLabel('吉他演奏方案').selectOption('continuous');
  await page.getByRole('button',{name:'Play score',exact:true}).click();
  await expect.poll(()=>!!held).toBe(true);
  await page.getByLabel('吉他演奏方案').selectOption('sparse');
  await held!.fulfill({json:preview});
  await expect(page.getByRole('button',{name:'Play score',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Pause score',exact:true})).toHaveCount(0);
  await expect(page.getByText(/本次處理 1 段和弦/)).toHaveCount(0);
});

test('late MIDI is discarded on mode change and failed request is visible',async({page})=>{
  let held:Route|undefined;let downloads=0;
  page.on('download',()=>downloads++);
  await page.route('**/scores/chord-entry-performance',r=>{held=r;});
  await page.getByLabel('吉他演奏方案').selectOption('continuous');
  await page.getByRole('button',{name:'Download MIDI',exact:true}).click();
  await expect.poll(()=>!!held).toBe(true);
  await page.getByRole('button',{name:'回原版演奏',exact:true}).click();
  await held!.fulfill({contentType:'audio/midi',body:'stale-midi'});
  await expect(page.getByRole('button',{name:'Download MIDI',exact:true})).toBeEnabled();
  expect(downloads).toBe(0);
  await page.unroute('**/scores/chord-entry-performance');
  await page.route('**/scores/chord-entry-performance',r=>r.fulfill({status:422,body:'演奏預覽暫時不可用'}));
  await page.getByLabel('吉他演奏方案').selectOption('continuous');
  await page.getByRole('button',{name:'Download MIDI',exact:true}).click();
  await expect(page.getByText('演奏預覽暫時不可用',{exact:true})).toBeVisible();
});

test('editing score resets mode and invalidates a pending preview',async({page})=>{
  let held:Route|undefined;
  await page.route('**/scores/chord-entry-performance',r=>{held=r;});
  await page.getByLabel('吉他演奏方案').selectOption('continuous');
  await page.getByRole('button',{name:'Play score',exact:true}).click();
  await expect.poll(()=>!!held).toBe(true);
  await page.locator('details').evaluateAll(nodes=>nodes.forEach(n=>(n as HTMLDetailsElement).open=true));
  await page.getByLabel('First detected beat in bar').selectOption('2');
  await expect(page.getByLabel('吉他演奏方案')).toHaveValue('original');
  await held!.fulfill({json:preview});
  await expect(page.getByRole('button',{name:'Pause score',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  await expect(page.getByLabel('First detected beat in bar')).toHaveValue('1');
  await expect(page.getByLabel('吉他演奏方案')).toHaveValue('original');
});

test('focused workspace has a direct accompaniment entry',async({page})=>{
  await page.evaluate(()=>localStorage.setItem('guitarscribe.workspaceMode','focus'));
  await page.reload();
  await expect(page.getByLabel('吉他演奏方案')).toBeHidden();
  await page.getByRole('button',{name:'伴奏演奏',exact:true}).click();
  await expect(page.getByLabel('吉他演奏方案')).toBeVisible();
  await expect(page.getByLabel('吉他演奏方案')).toBeFocused();
});
