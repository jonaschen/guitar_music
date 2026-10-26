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

test('entry audit is read-only, uses active mode and clears stale findings',async({page})=>{
  const bodies:any[]=[];
  const issues=[{right_id:'c',measure:7,old_chord:'Am',new_chord:'Em',downbeat_seconds:4,
    boundary_lag_seconds:.019,wait_after_downbeat_seconds:.46,previous_beat_seconds:3.5,contains_manual_edit:false}];
  await page.route('**/scores/chord-entry-audit',r=>{bodies.push(r.request().postDataJSON());return r.fulfill({json:{issues}});});
  await page.getByText('換和弦入口檢查',{exact:true}).click();
  await page.getByRole('button',{name:'檢查目前演奏',exact:true}).click();
  await expect(page.getByText(/第一拍後 0.46 秒/)).toBeVisible();
  await page.getByRole('button',{name:'定位 Bar 7 前一拍',exact:true}).click();
  await expect(page.getByLabel('Playback position',{exact:true})).toHaveValue('3.5');
  await expect(page.getByRole('button',{name:'Undo',exact:true})).toBeDisabled();
  await page.getByLabel('吉他演奏方案').selectOption('continuous');
  await expect(page.getByText(/第一拍後 0.46 秒/)).toHaveCount(0);
  await page.getByRole('button',{name:'檢查目前演奏',exact:true}).click();
  await expect.poll(()=>bodies.length).toBe(2);
  expect(bodies.map(b=>b.mode)).toEqual(['original','continuous']);
  expect(bodies[0].score).toEqual(bodies[1].score);
});

test('grid preview applies explicitly to playback and MIDI and Undo restores score',async({page})=>{
  let original:any;let candidate:any;let saves=0;
  page.on('request',r=>{if(r.method()==='POST' && /\/revisions$/.test(r.url())) saves++;});
  await page.route('**/scores/chord-grid-candidate',r=>{
    original=r.request().postDataJSON();candidate=structuredClone(original);
    candidate.chords[0].end=7.5;candidate.provenance.parameters.chord_grid_candidate='nearest-eighth-v1';
    return r.fulfill({json:{score:candidate,report:{changes:[{}],protected:[],unquantized_edges:[]}}});
  });
  await page.route('**/scores/chord-entry-performance',r=>r.fulfill({json:preview}));
  await page.getByLabel('吉他演奏方案').selectOption('continuous');
  await page.getByText('整理伴奏拍長（八分拍格・實驗）',{exact:true}).click();
  await page.getByRole('button',{name:'預覽拍長整理',exact:true}).click();
  await expect(page.getByText(/預計調整 1 段和弦/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Undo',exact:true})).toBeDisabled();
  await expect(page.getByLabel('吉他演奏方案')).toHaveValue('continuous');
  await page.getByRole('button',{name:'Play score',exact:true}).click();
  await expect(page.getByRole('button',{name:'Pause score',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'套用拍長整理（可 Undo）',exact:true}).click();
  await expect(page.getByLabel('吉他演奏方案')).toHaveValue('original');
  await expect(page.getByRole('button',{name:'Pause score',exact:true})).toHaveCount(0);
  const playback=page.waitForRequest('**/scores/playback/manifest');
  await page.getByRole('button',{name:'Play score',exact:true}).click();
  expect((await playback).postDataJSON()).toEqual(candidate);
  await page.getByRole('button',{name:'Stop score',exact:true}).click();
  const midi=page.waitForRequest('**/scores/midi');const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download MIDI',exact:true}).click();
  expect((await midi).postDataJSON()).toEqual(candidate);await download;
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  const restored=page.waitForRequest('**/scores/playback/manifest');
  await page.getByRole('button',{name:'Play score',exact:true}).click();
  expect((await restored).postDataJSON()).toEqual(original);expect(saves).toBe(0);
});

test('grid rejects stale responses and displays failures without changing score',async({page})=>{
  let held:Route|undefined;
  await page.route('**/scores/chord-grid-candidate',r=>{held=r;});
  await page.getByText('整理伴奏拍長（八分拍格・實驗）',{exact:true}).click();
  await page.getByRole('button',{name:'預覽拍長整理',exact:true}).click();
  await expect.poll(()=>!!held).toBe(true);
  await page.locator('details').evaluateAll(nodes=>nodes.forEach(n=>(n as HTMLDetailsElement).open=true));
  await page.getByLabel('First detected beat in bar').selectOption('2');
  await held!.fulfill({json:{score,report:{changes:[{}],protected:[],unquantized_edges:[]}}});
  await expect(page.getByRole('button',{name:'套用拍長整理（可 Undo）',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  await page.unroute('**/scores/chord-grid-candidate');
  await page.route('**/scores/chord-grid-candidate',r=>r.fulfill({status:422,body:'invalid'}));
  await page.getByRole('button',{name:'預覽拍長整理',exact:true}).click();
  await expect(page.getByRole('alert').filter({hasText:'無法整理這份譜'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Undo',exact:true})).toBeDisabled();
});
