import {readFileSync} from "node:fs";
const acceptedGrid=JSON.parse(readFileSync(new URL("./fixtures/accepted-chord-grid.json",import.meta.url),"utf8"));
import {removeChordSlice} from "../src/chordSlice";
import {beatCoordinate, shiftByBeats, retimeChord} from "../src/chordTiming";
import {test, expect} from '@playwright/test';
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

const guideShape=(symbol:string,frets:Array<number|null>,capo=0)=>({id:symbol+'-guide',symbol,shape_symbol:symbol,frets,fingers:[null,3,2,null,1,null],base_fret:1,capo,difficulty:1,tags:[]});
for(const unmetered of [false,true])for(const originalSource of [false,true])test(`transpose preserves clear minor-key meaning and playable mode (${unmetered},source=${originalSource})`,async({page})=>{
  const key={key:'B',mode:'minor'};
  const working={...score,analysis:{...score.analysis,key:'B',mode:'minor',timing_status:unmetered?'unmetered':'metered',bpm:unmetered?0:120,time_signature:unmetered?'':'4/4'},beats:unmetered?[]:score.beats,
    key_context:{...score.key_context,source:key,target:key,shape:key,sounding:key},chords:[{...score.chords[0],symbol:'Bm'}]};
  await setup(page,working);
  if(originalSource)await page.getByLabel('播放聲音',{exact:true}).selectOption('source');
  await page.route('**/scores/transpose',r=>{
    const body=r.request().postDataJSON();expect(body.semitones).toBe(-4);
    return r.fulfill({json:{...working,analysis:{...working.analysis,key:'G'},provenance:body.score.provenance,key_context:{...working.key_context,target:{key:'G',mode:'minor'},shape:{key:'G',mode:'minor'},sounding:{key:'G',mode:'minor'},transpose_semitones:-4,audio_matches_notation:false},chords:[{...working.chords[0],symbol:'Gm'}]}});
  });
  await expect(page.getByText('原曲推估：B小調（和弦估計，未確認）',{exact:true})).toBeVisible();
  await page.getByLabel('歌曲調性',{exact:true}).selectOption('G');
  await expect(page.getByLabel('播放聲音',{exact:true})).toHaveValue(originalSource?'source':'guitar');
  await expect(page.getByRole('button',{name:'播放',exact:true})).toBeEnabled();
  await expect(page.getByText(originalSource?'伴奏已移調；目前播放原曲原調。回到原調後才能合奏。':'伴奏已移調；目前以吉他播放。回到原調後才能合奏。',{exact:true})).toBeVisible();
  await expect(page.getByLabel('播放聲音').locator('option[value=mix]')).toHaveAttribute('disabled','');
  if(!originalSource){
    let compiled:any;await page.route('**/scores/playback/manifest',r=>{compiled=r.request().postDataJSON();return r.fulfill({json:{revision:'transposed',duration_seconds:8,bpm:0,time_signature:'',events:[{id:'g',track:'guitar',start:0,end:8,sustain_end:8,pitches:[55,58,62],pitch_offsets:[0,0,0],pitch_velocities:[98,98,98],velocity:98,source_id:'c'}]}})});
    await page.getByRole('button',{name:'播放',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
    expect(compiled.chords[0].symbol).toBe('Gm');expect(compiled.key_context.source).toEqual(key);
    await page.getByRole('button',{name:'暫停',exact:true}).click();
  }
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByLabel('歌曲調性',{exact:true})).toHaveValue('B');
  await expect(page.getByLabel('播放聲音').locator('option[value=mix]')).not.toHaveAttribute('disabled');
});
for(const unmetered of [false,true])test(`fingering guide is readable without editing (${unmetered?'timeline':'bars'})`,async({page})=>{
  const working={...score,analysis:{...score.analysis,timing_status:unmetered?'unmetered':'metered',bpm:unmetered?0:120,time_signature:unmetered?'':'4/4'},beats:unmetered?[]:score.beats,
    chords:[{...score.chords[0],end:2},{...score.chords[0],id:'c2',start:2,end:4},{...score.chords[0],id:'g',symbol:'G',start:4,end:8}]};
  await page.route('**/chord-voicings?*',r=>{const symbol=new URL(r.request().url()).searchParams.get('symbol')!;return r.fulfill({json:[guideShape(symbol,symbol==='C'?[null,3,2,0,1,0]:[3,2,0,0,0,3])]});});
  await setup(page,working);let writes=0;await page.route('**/revisions',r=>{writes++;return r.fulfill({json:{revision_id:'unexpected'}})});
  const guide=page.locator('.chord-fingerings');await expect(guide.getByLabel('查看和弦按法')).toHaveCount(0);
  await guide.getByText('和弦按法',{exact:true}).click();await expect(guide.getByRole('img',{name:'C chord diagram'})).toBeVisible();
  await expect(guide.getByLabel('查看和弦按法').locator('option')).toHaveCount(2);
  await guide.getByLabel('查看和弦按法').selectOption({label:'G'});await expect(guide.getByRole('img',{name:'G chord diagram'})).toBeVisible();
  await expect(guide.getByLabel('和弦品格')).toHaveText('品格：3 · 2 · 0 · 0 · 0 · 3');
  for(const width of [320,390,1440]){await page.setViewportSize({width,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
  await page.waitForTimeout(1400);expect(writes).toBe(0);await expect(page.getByRole('heading',{name:/修改/})).toHaveCount(0);
});

test('fingering guide retains the selected stored shape and explains capo-relative frets',async({page})=>{
  const open=guideShape('C',[null,3,2,0,1,0],2),chosen={...guideShape('C',[8,10,10,9,8,8],2),id:'chosen',base_fret:8};
  await setup(page,{...score,analysis:{...score.analysis,capo:2},chords:[{...score.chords[0],available_voicings:[open,chosen],voicing_id:'chosen'}]});
  const guide=page.locator('.chord-fingerings');await guide.getByText('和弦按法',{exact:true}).click();
  await expect(guide.getByLabel('和弦品格')).toHaveText('品格：8 · 10 · 10 · 9 · 8 · 8');
  await expect(guide).toContainText('Capo 第 2 品；圖中品格從移調夾起算。');
});

test('late fingering lookup cannot replace a newly selected chord',async({page})=>{
  let release!:()=>void;const hold=new Promise<void>(resolve=>{release=resolve});
  await page.route('**/chord-voicings?*',async r=>{const symbol=new URL(r.request().url()).searchParams.get('symbol')!;if(symbol==='C')await hold;await r.fulfill({json:[guideShape(symbol,[3,2,0,0,0,3])]}).catch(()=>{});});
  await setup(page,{...score,chords:[{...score.chords[0],end:4},{...score.chords[0],id:'g',symbol:'G',start:4}]});
  const guide=page.locator('.chord-fingerings');await guide.getByText('和弦按法',{exact:true}).click();
  await guide.getByLabel('查看和弦按法').selectOption({label:'G'});await expect(guide.getByRole('img',{name:'G chord diagram'})).toBeVisible();release();
  await expect(guide.getByRole('img',{name:'C chord diagram'})).toHaveCount(0);
});

test('an incomplete shape is not presented as a full chord fingering',async({page})=>{
  await page.route('**/chord-voicings?*',r=>r.fulfill({json:[{...guideShape('C',[null,3,null,null,null,null]),tags:['incomplete']}]}));
  await setup(page);const guide=page.locator('.chord-fingerings');await guide.getByText('和弦按法',{exact:true}).click();
  await expect(guide.getByRole('status')).toHaveText('目前沒有這個和弦的完整按法。');await expect(guide.getByRole('img')).toHaveCount(0);
});

test('cropped pickup has one opening cell; editing does not invent or renumber full bars',async({page})=>{
  const working={...score,beats:[{time:.22,beat:4,measure:0,confidence:0},
    ...Array.from({length:15},(_,i)=>({time:.64+i*.5,beat:i%4+1,measure:Math.floor(i/4)+1,confidence:0}))]};
  await setup(page,working);
  const sheet=page.getByLabel('和弦譜',{exact:true});
  await expect(sheet.getByLabel('起始片段',{exact:true})).toHaveCount(1);
  await expect(sheet.getByLabel('Bar -1',{exact:true})).toHaveCount(0);
  await expect(sheet.getByLabel('Bar 0',{exact:true})).toHaveCount(0);
  await expect(sheet.getByLabel('Bar 1',{exact:true})).toBeVisible();
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 起始片段 的 C',exact:true}).click();
  await expect(page.getByRole('heading',{name:'修改 起始片段的 C',exact:true})).toBeVisible();
  await page.getByLabel('和弦名稱',{exact:true}).fill('G');
  let saved:any;await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'pickup-edited'}})});
  await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  await expect.poll(()=>saved?.score?.chords?.[0]?.end).toBe(.64);
  expect(saved.score.beats).toEqual(working.beats);
  await expect(sheet.getByLabel('Bar 1',{exact:true}).getByRole('button')).toContainText('C');
});

async function setup(page:any, working:any=score, timingView?:string) {
  await page.addInitScript(()=>{localStorage.setItem('guitarscribe.editorView','melody');localStorage.setItem('guitarscribe.workspaceMode','full');});
  await page.route('**/api/v1/capabilities',r=>r.fulfill({json:{melody_available:true,youtube_enabled:true,vocal_separation_enabled:true}}));
  const archived={...working,melody:[{id:'n',start:0,end:1,midi:60,note:'C4',confidence:1,origin:'model',edited:false}]};
  await page.route('**/api/v1/jobs/product-job',r=>r.fulfill({json:{id:'product-job',status:'completed',progress:100,artifacts:[],score:archived}}));
  await page.route('**/api/v1/jobs/product-job/audio',r=>r.fulfill({status:404,body:''}));
  await page.route('**/revisions/*/history',r=>r.fulfill({json:[]}));
  await page.route('**/revisions',r=>r.fulfill({json:{revision_id:'auto-saved'}}));
  await page.route('**/rhythm-patterns?*',r=>r.fulfill({json:[]}));
  await page.goto('/?job=product-job&view=melody'+(timingView?`&timingView=${timingView}`:''));
  await expect(page.getByRole('region',{name:'和弦核對'})).toBeVisible();
  return archived;
}
test('frozen default ignores archived preference; saved data retained, accompaniment MIDI excludes notes',async({page})=>{
  const archived=await setup(page);
  await expect(page.getByRole('button',{name:'旋律編輯（實驗）'})).toHaveCount(0);
  await expect(page.getByLabel('Tab start bar')).toHaveCount(0);
  let saved:any, exported:any;
  await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'saved'}});});
  await page.getByText('版本歷史與還原',{exact:true}).click();
  await page.getByRole('button',{name:'保存目前工作版本',exact:true}).click();
  await expect.poll(()=>saved?.score?.melody?.length).toBe(1);
  expect(saved.score.melody).toEqual(archived.melody);
  await page.route('**/scores/midi',r=>{exported=r.request().postDataJSON();return r.fulfill({body:'midi',contentType:'audio/midi'});});
  await page.getByText('下載與備份',{exact:true}).click();
  await page.getByRole('button',{name:'下載伴奏 MIDI',exact:true}).click();
  await expect.poll(()=>exported?.melody).toEqual([]);
  await page.getByText('診斷工具',{exact:true}).click();
  await page.getByRole('button',{name:'伴奏設定與拍長整理'}).click();
  await expect(page.getByLabel('melody track',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Tab start bar')).toHaveCount(0);
});
for(const width of [320,390,768,1440])test(`responsive notation and progressive controls at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:844});await setup(page);
  await expect(page.getByLabel('歌曲調性')).toBeVisible();
  await expect(page.getByLabel('歌曲 Capo')).toBeVisible();
  await expect(page.getByRole('button',{name:'復原',exact:true})).toBeHidden();
  const bars=page.locator('.notation-measure');expect(await bars.count()).toBe(4);
  const bounds=await bars.evaluateAll(els=>els.map(el=>el.getBoundingClientRect().top));
  expect(new Set(bounds).size).toBe(width<=640?2:1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`test-results/chord-product-${width}.png`,fullPage:true});
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 Bar 3 的 C',exact:true}).click();
  await expect(page.getByRole('region',{name:'修改和弦'})).toBeVisible();
  await expect(page.getByLabel('吉他演奏方案')).toBeHidden();
});

test('compact rename clears stale fingering, preserves melody, and Undo restores the chord',async({page})=>{
  await setup(page);
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 Bar 1 的 C',exact:true}).click();
  await page.getByLabel('和弦名稱',{exact:true}).fill('G');
  await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 1 的 G',exact:true})).toBeVisible();
  let saved:any;await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'edited'}});});
  await expect.poll(()=>saved?.score?.chords[0].symbol).toBe('G');
  expect(saved.score.chords[0].shape_symbol).toBe('G');
  expect(saved.score.chords[0].available_voicings).toEqual([]);
  expect(saved.score.melody).toHaveLength(1);
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 1 的 C',exact:true})).toBeVisible();
});

test('new YouTube analysis disables melody and explains unsupported timing without losing work',async({page})=>{
  await setup(page);let submitted:any;
  await page.route('**/api/v1/youtube-jobs',r=>{submitted=r.request().postDataJSON();return r.fulfill({json:{id:'failed-new',status:'queued',progress:0}});});
  await page.route('**/api/v1/jobs/failed-new',r=>r.fulfill({json:{id:'failed-new',status:'failed',progress:30,error:'Inconsistent meter or missing beats/downbeats; explicit review required'}}));
  await page.getByRole('button',{name:'分析新曲目',exact:true}).click();
  await page.getByLabel('YouTube video URL').fill('https://www.youtube.com/watch?v=WObbdwgB41c');
  await page.getByRole('button',{name:'Start analysis',exact:true}).click();
  await expect.poll(()=>submitted?.melody_mode).toBe('off');
  expect(submitted.separate_vocals).toBe(false);
  await expect(page.getByRole('alert')).toContainText('拍點或小節位置尚無法可靠確認');
  await page.getByRole('button',{name:'回到歌曲',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Entry preview test',exact:true})).toBeVisible();
});

test('invalid pasted links are explained before submission',async({page})=>{
  await setup(page);await page.getByRole('button',{name:'分析新曲目',exact:true}).click();
  await page.getByLabel('YouTube video URL').fill('https://example.com/not-a-song');
  await expect(page.getByLabel('YouTube video URL')).toHaveAttribute('aria-invalid','true');
  await expect(page.getByRole('button',{name:'Start analysis',exact:true})).toBeDisabled();
  await expect(page.getByText(/請貼上單一 YouTube/)).toBeVisible();
  await page.getByLabel('YouTube video URL').fill('https://www.youtube.com/watch?v=WObbdwgB41c&list=RDWObbdwgB41c');
  await expect(page.getByRole('button',{name:'Start analysis',exact:true})).toBeEnabled();
});
test('autosave failure keeps edits, manual retry saves; redo and original restore stay reversible',async({page})=>{
  await setup(page);await page.route('**/revisions',r=>r.fulfill({status:503,body:'unavailable'}));
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 Bar 1 的 C',exact:true}).click();
  await page.getByLabel('和弦名稱',{exact:true}).fill('Am');await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('暫時無法保存');
  await expect(page.getByRole('button',{name:'編輯 Bar 1 的 Am',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'復原',exact:true}).click();await page.getByRole('button',{name:'重做',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 1 的 Am',exact:true})).toBeVisible();
  await page.route('**/revisions',r=>r.fulfill({json:{revision_id:'retried'}}));
  await page.getByText('版本歷史與還原',{exact:true}).click();
  await page.getByRole('button',{name:'保存目前工作版本',exact:true}).click();
  await expect(page.locator('.autosave-status')).toContainText('已保存');
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'還原原始分析',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 1 的 C',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 1 的 Am',exact:true})).toBeVisible();
});

test('normal chord click seeks and plays; editing is explicit',async({page})=>{
  await setup(page);
  await page.route('**/scores/playback/manifest',r=>r.fulfill({json:{revision:'test',duration_seconds:8,bpm:120,time_signature:'4/4',events:[{id:'g',track:'guitar',start:0,end:8,sustain_end:8,pitches:[48],pitch_offsets:[0],pitch_velocities:[98],velocity:98,source_id:'c'}]}}));
  await page.getByLabel('播放聲音',{exact:true}).selectOption('guitar');
  await page.getByRole('button',{name:'播放 Bar 3 的 C',exact:true}).click();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  await expect(page.locator('.playback-status')).toContainText(/播放中 · [4-7]\./);
  await expect(page.getByRole('region',{name:'修改和弦'})).toHaveCount(0);
  await page.getByRole('button',{name:'暫停',exact:true}).click();
});


test('beat editing follows variable beat durations and protects gaps and neighbours',()=>{
  const s:any={...score,beats:[0,.4,1,1.8,2.8,4].map((time,i)=>({time,beat:i%4+1,measure:1})),chords:[{...score.chords[0],end:1},{...score.chords[0],id:'g',symbol:'G',start:1,end:4}]};
  const end=shiftByBeats(s,1,.5);expect(end).toBeCloseTo(1.4);
  const next=retimeChord(s,'c',0,end);expect(next.chords[1].start).toBeCloseTo(end);
  expect(beatCoordinate(next,end)-beatCoordinate(next,0)).toBeCloseTo(2.5);
  expect(s.chords[0].end).toBe(1);
  expect(()=>retimeChord(s,'c',0,4)).toThrow(/相鄰和弦太短/);
  expect(()=>retimeChord(s,'c',0,9)).toThrow(/歌曲範圍/);
  const gap={...s,chords:[s.chords[0],{...s.chords[1],start:2}]};
  expect(retimeChord(gap,'c',0,1.4).chords[1].start).toBe(2);
  expect(()=>retimeChord(gap,'c',0,2.2)).toThrow(/跨過其他和弦/);
  expect(()=>shiftByBeats({...s,beats:[]},1,.5)).toThrow(/拍點不足/);
});

test('half beat edit moves the shared boundary, auto-saves, compiles and undoes both chords',async({page})=>{
  const working={...score,chords:[{...score.chords[0],end:2},{...score.chords[0],id:'g',symbol:'G',start:2,end:8}]};
  await setup(page,working);let saved:any,compiled:any;
  await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'timed'}});});
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 Bar 1 的 C',exact:true}).click();
  await page.getByRole('button',{name:'增加半拍',exact:true}).click();
  await expect(page.getByLabel('目前和弦拍長')).toContainText('4.5 拍');
  await expect.poll(()=>saved?.score?.chords[0].end).toBe(2.25);
  expect(saved.score.chords[1].start).toBe(2.25);expect(saved.score.melody).toHaveLength(1);
  await page.route('**/scores/playback/manifest',r=>{compiled=r.request().postDataJSON();return r.fulfill({json:{revision:'test',duration_seconds:8,bpm:120,time_signature:'4/4',events:[]}});});
  await page.getByLabel('播放聲音',{exact:true}).selectOption('guitar');await page.getByRole('button',{name:'播放',exact:true}).click();
  await expect.poll(()=>compiled?.chords[0].end).toBe(2.25);expect(compiled.chords[1].start).toBe(2.25);
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByLabel('目前和弦拍長')).toContainText('4 拍');
  await expect.poll(()=>saved?.score?.chords[1].start).toBe(2);
  await page.getByRole('button',{name:'重做',exact:true}).click();
  await expect(page.getByLabel('目前和弦拍長')).toContainText('4.5 拍');
  await page.getByRole('button',{name:'調整時間與指型',exact:true}).click();
  await expect(page.getByLabel('Drag chord end boundary')).toHaveAttribute('max','7.9');
  await page.locator('.timing-fields input').nth(1).fill('2.5');
  await page.getByRole('button',{name:'Save timing',exact:true}).click();
  await expect.poll(()=>saved?.score?.chords[0].end).toBe(2.5);
  expect(saved.score.chords[1].start).toBe(2.5);
});

test('renaming a continuation in Bar 7 preserves Bars 6 and 8, survives reload and undoes atomically',async({page})=>{
  const working={...score,song:{...score.song,duration_seconds:16},beats:Array.from({length:32},(_,i)=>({time:i*.5,beat:i%4+1,measure:Math.floor(i/4)+1,confidence:1})),chords:[
    {...score.chords[0],id:'before',symbol:'C',end:9.5},
    {...score.chords[0],id:'span',symbol:'Am',start:9.5,end:15.5},
    {...score.chords[0],id:'after',symbol:'G',start:15.5,end:16},
  ]};
  await setup(page,working);let saved:any;
  await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'bar-seven'}});});
  await page.route('**/revisions/bar-seven',r=>r.fulfill({json:saved.score}));
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 Bar 7 的 Am',exact:true}).click();
  await expect(page.getByRole('heading',{name:'修改 第 7 小節的 Am',exact:true})).toBeVisible();
  await page.getByLabel('和弦名稱',{exact:true}).fill('Em');await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 6 的 Am',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'編輯 Bar 7 的 Em',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'編輯 Bar 8 的 Am',exact:true})).toBeVisible();
  await expect.poll(()=>saved?.score?.chords?.length).toBe(5);
  expect(saved.score.chords.slice(1,4).map((c:any)=>[c.symbol,c.start,c.end])).toEqual([['Am',9.5,12],['Em',12,14],['Am',14,15.5]]);
  expect(new Set(saved.score.chords.map((c:any)=>c.id)).size).toBe(5);
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 7 的 Am',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'重做',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 7 的 Em',exact:true})).toBeVisible();
  await page.reload();await expect(page.getByRole('button',{name:'播放 Bar 6 的 Am',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'播放 Bar 7 的 Em',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'播放 Bar 8 的 Am',exact:true})).toBeVisible();
});


test('stable review entry loads accepted Bar 7 revision without restoring remembered baseline',async({page})=>{
  await setup(page);
  await page.route('**/revisions/4384c826-a4f0-4442-b1d4-ef7bbc7888f4',r=>r.fulfill({json:{...score,song:{...score.song,title:'Accepted Bar 7'}}}));
  await page.goto('/review.html');
  await expect(page).toHaveURL(/revision=4384c826-a4f0-4442-b1d4-ef7bbc7888f4/);
  await expect(page.getByRole('heading',{name:'Accepted Bar 7',exact:true})).toBeVisible();
});


test('bar deletion preserves outside spans and gaps without mutating original',()=>{
  const c:any={...score.chords[0],start:0,end:8};
  const removed=removeChordSlice([c],'c',{start:2,end:4,bar:2});
  expect(removed.map(x=>[x.start,x.end])).toEqual([[0,2],[4,8]]);
  expect(new Set(removed.map(x=>x.id)).size).toBe(2);expect(c.end).toBe(8);
  const gap:any=[{...c,id:'p',end:1},{...c,id:'g',symbol:'G',start:1.5,end:4}];
  expect(removeChordSlice(gap,'g',{start:0,end:2,bar:1}).map(x=>[x.start,x.end])).toEqual([[0,1],[2,4]]);
});

test('deleting trailing fragment fills with previous chord, preserves next bar, saves and undoes',async({page})=>{
  const working={...score,chords:[{...score.chords[0],end:1.99},{...score.chords[0],id:'g',symbol:'G',start:1.99,end:8}]};
  await setup(page,working);let saved:any;
  await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'removed-fragment'}});});
  await page.route('**/revisions/removed-fragment',r=>r.fulfill({json:saved.score}));
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  const fragment=page.getByRole('button',{name:'編輯 Bar 1 的 G',exact:true});await expect(fragment).toHaveAttribute('title',/0.02 拍/);await fragment.click();
  await expect(page.getByLabel('本小節片段拍長')).toContainText('0.02 拍');
  await page.getByRole('button',{name:'刪除此小節內的片段',exact:true}).click();
  await expect(fragment).toHaveCount(0);await expect(page.getByRole('button',{name:'編輯 Bar 2 的 G',exact:true})).toBeVisible();
  await expect.poll(()=>saved?.score?.chords[0].end).toBe(2);expect(saved.score.chords[1].start).toBe(2);
  expect(saved.score.melody).toHaveLength(1);
  await page.getByRole('button',{name:'復原',exact:true}).click();await expect(fragment).toBeVisible();
  await page.getByRole('button',{name:'重做',exact:true}).click();await expect(fragment).toHaveCount(0);
  await page.reload();await expect(page.getByRole('button',{name:'播放 Bar 1 的 G',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'播放 Bar 2 的 G',exact:true})).toBeVisible();
});


test('accepted grid renders full-bar chords and real half-bar changes, without boundary slivers',async({page})=>{
  await setup(page,{...score,...acceptedGrid});
  const sheet=page.getByLabel('和弦譜',{exact:true});
  for(const [bar,symbol] of [[5,'G'],[6,'Am'],[7,'Em'],[8,'F'],[9,'C'],[14,'Am'],[15,'Em']]){
    const cell=sheet.getByLabel(`Bar ${bar}`,{exact:true});
    await expect(cell.getByRole('button')).toHaveCount(1);
    await expect(cell.getByRole('button',{name:`播放 Bar ${bar} 的 ${symbol}`,exact:true})).toBeVisible();
  }
  await expect(sheet.getByLabel('Bar 3',{exact:true}).getByRole('button')).toHaveCount(2);
  await expect(sheet.getByLabel('Bar 3',{exact:true}).getByText('2 拍',{exact:true})).toHaveCount(2);
  await expect(sheet).not.toContainText('約');
  await expect(sheet).not.toContainText('0.02 拍');
});

const timelineScore={...score,analysis:{...score.analysis,timing_status:'unmetered',bpm:0,time_signature:''},beats:[],rhythm:{...score.rhythm,display:[]},chords:[{...score.chords[0],end:3.217},{...score.chords[0],id:'g',symbol:'G',start:3.217,end:8}]};

const partialScore={...timelineScore,song:{...timelineScore.song,duration_seconds:12},chords:[{...score.chords[0],end:12}]};
const partialPreview={job_id:'product-job',duration_seconds:12,source_start_seconds:0,covered_seconds:8,
  regions:[{start:2,end:10,beats_per_bar:4,bars:Array.from({length:4},(_,i)=>({start:2+i*2,end:4+i*2,beats:Array.from({length:5},(_,j)=>2+i*2+j*.5)}))}]};

for(const width of [320,390,1440])test(`automatic local reading candidate starts in draft and preserves source editing (${width})`,async({page})=>{
  await page.setViewportSize({width,height:844});
  await page.route('**/timing-preview',r=>r.fulfill({json:partialPreview}));
  await setup(page,partialScore,'auto');
  const preview=page.getByLabel('局部小節預覽',{exact:true});
  await expect(preview).toBeVisible();
  await expect(preview.locator('.notation-measure')).toHaveCount(4);
  await expect(preview.locator('.partial-unknown')).toHaveCount(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:'時間表',exact:true}).click();
  await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'局部譜 · 待確認',exact:true}).click();
  await expect(preview).toBeVisible();
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'到時間表編輯',exact:true}).click();
  await expect(preview).toHaveCount(0);
  await page.getByRole('button',{name:'編輯 0.00 秒的 C',exact:true}).click();
  expect(Number(await page.getByLabel('結束時間（秒）',{exact:true}).inputValue())).toBe(12);
  await page.getByLabel('和弦名稱',{exact:true}).fill('Em');
  await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  await page.getByRole('button',{name:'完成編輯',exact:true}).click();
  await expect(preview.getByRole('button',{name:'播放 4.00 秒的 Em',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(preview.getByRole('button',{name:'播放 4.00 秒的 C',exact:true})).toBeVisible();
});

for(const bad of [null,{start:2,end:10,beats_per_bar:4,bars:null}])test(`automatic local candidate ignores malformed region (${JSON.stringify(bad)})`,async({page})=>{
  await page.route('**/timing-preview',r=>r.fulfill({json:{...partialPreview,regions:[bad]}}));
  await setup(page,partialScore,'auto');
  await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await expect(page.getByLabel('讀譜方式',{exact:true})).toHaveCount(0);
});

test('automatic local reading discards delayed old-song preview after revision switch and supports Undo',async({page})=>{
  let release!:()=>void;const hold=new Promise<void>(r=>{release=r});
  await page.addInitScript(()=>{
    localStorage.setItem('guitarscribe.savedVersion',JSON.stringify({id:'next-revision',label:'Next',jobId:'next-job'}));
    localStorage.setItem('guitarscribe.melodyRevision.product-job','next-revision');
  });
  await page.route('**/jobs/product-job/timing-preview',async r=>{await hold;await r.fulfill({json:partialPreview}).catch(()=>{});});
  const nextScore={...partialScore,chords:[{...partialScore.chords[0],symbol:'G'}],provenance:{...partialScore.provenance,parameters:{analysis_source_job_id:'next-job'}}};
  await page.route('**/revisions/next-revision',r=>r.fulfill({json:nextScore}));
  await page.route('**/jobs/next-job',r=>r.fulfill({json:{id:'next-job',status:'completed',score:nextScore}}));
  await page.route('**/jobs/next-job/timing-preview',r=>r.fulfill({json:{...partialPreview,job_id:'next-job'}}));
  try{
  await setup(page,partialScore,'auto');
  await page.getByText('版本歷史與還原',{exact:true}).click();
  await page.getByRole('button',{name:'恢復上次保存版本',exact:true}).click();
  await page.getByRole('button',{name:'確認恢復版本（可 Undo）',exact:true}).click();
  const preview=page.getByLabel('局部小節預覽',{exact:true});
  await expect(preview.getByRole('button',{name:'播放 4.00 秒的 G',exact:true})).toBeVisible();
  release();
  await expect(preview.getByRole('button',{name:'播放 4.00 秒的 G',exact:true})).toBeVisible();
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'到時間表編輯',exact:true}).click();
  await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'還原上一步',exact:true}).click();
  await expect(preview.getByRole('button',{name:'播放 4.00 秒的 C',exact:true})).toBeVisible();
  }finally{release();}
});

for(const metered of [false,true])test(`automatic local candidate retains original view without usable local evidence (${metered?'metered':'missing'})`,async({page})=>{
  await page.route('**/timing-preview',r=>r.fulfill({status:404}));
  await setup(page,metered?score:partialScore,'auto');
  await expect(page.getByLabel('讀譜方式',{exact:true})).toHaveCount(0);
  if(metered)await expect(page.locator('.notation-measure')).toHaveCount(4);
  else await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
});

for(const width of [320,390])for(const draft of [false,true])test(`long-sheet pause stays clickable after middle seek and manual scroll (${width},${draft?'draft':'timeline'})`,async({page})=>{
  const long={...timelineScore,song:{...timelineScore.song,duration_seconds:315},chords:Array.from({length:158},(_,i)=>({...score.chords[0],id:`long-${i}`,start:i*2,end:Math.min(315,(i+1)*2)}))};
  const preview={...partialPreview,duration_seconds:315,covered_seconds:204,regions:[{start:40,end:244,beats_per_bar:4,bars:Array.from({length:51},(_,i)=>({start:40+i*4,end:44+i*4,beats:Array.from({length:5},(_,j)=>40+i*4+j)}))}]};
  await page.setViewportSize({width,height:844});
  await page.route('**/timing-preview',r=>r.fulfill({json:preview}));
  await setup(page,long,draft?'auto':undefined);
  await page.route('**/scores/playback/manifest',r=>r.fulfill({json:{revision:'long',duration_seconds:315,bpm:0,time_signature:'',events:[{id:'c',track:'guitar',start:0,end:315,sustain_end:315,pitches:[48],pitch_offsets:[0],pitch_velocities:[98],velocity:98,source_id:'c'}]}}));
  await page.getByLabel('播放聲音',{exact:true}).selectOption('guitar');
  if(draft)await page.getByLabel('局部小節預覽',{exact:true}).getByRole('button',{name:'播放 120.00 秒的 C',exact:true}).click();
  else await page.getByRole('button',{name:'播放 120.00 秒的 C',exact:true}).click();
  const pause=page.getByRole('button',{name:'暫停',exact:true});await expect(pause).toBeVisible();
  await page.mouse.wheel(0,900);await page.waitForTimeout(250);
  await expect(pause).toBeInViewport();
  await pause.click({timeout:3000});
  await expect(page.getByRole('button',{name:'播放',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('complete metered sheet retains normal controls and unclipped editing after page clipping fix',async({page})=>{
  const long={...score,song:{...score.song,duration_seconds:315},beats:Array.from({length:630},(_,i)=>({time:i*.5,beat:i%4+1,measure:Math.floor(i/4)+1,confidence:1})),chords:[{...score.chords[0],end:315}]};
  await page.setViewportSize({width:390,height:844});await setup(page,long);
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 Bar 60 的 C',exact:true}).click();
  const editor=page.getByRole('region',{name:'修改和弦'});await expect(editor).toBeVisible();
  await page.getByLabel('和弦名稱',{exact:true}).scrollIntoViewIfNeeded();
  await expect(page.getByLabel('和弦名稱',{exact:true})).toBeInViewport();
  await page.getByLabel('和弦名稱',{exact:true}).fill('Em');
  await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 Bar 60 的 Em',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('local bar preview preserves gaps, score and playback; editing uses original seconds',async({page})=>{
  await page.route('**/timing-preview',r=>r.fulfill({json:partialPreview}));
  await setup(page,partialScore);
  let writes=0,compiled:any;await page.route('**/revisions',r=>{writes++;return r.fulfill({json:{revision_id:'partial-save'}})});
  await page.route('**/scores/playback/manifest',r=>{compiled=r.request().postDataJSON();return r.fulfill({json:{revision:'partial',duration_seconds:12,bpm:0,time_signature:'',events:[{id:'c',track:'guitar',start:0,end:12,sustain_end:12,pitches:[48],pitch_offsets:[0],pitch_velocities:[98],velocity:98,source_id:'c'}]}})});
  await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await page.getByLabel(/預覽可辨識的小節/).check();
  const preview=page.getByLabel('局部小節預覽',{exact:true});
  await expect(preview.locator('.notation-measure')).toHaveCount(4);
  await expect(preview.locator('.partial-unknown')).toHaveCount(2);
  await expect(preview.getByLabel('延續',{exact:true})).toHaveCount(5);
  for(const width of [320,390,1440]){await page.setViewportSize({width,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
  await page.getByLabel('播放聲音',{exact:true}).selectOption('guitar');
  await preview.getByRole('button',{name:'播放 4.00 秒的 C',exact:true}).click();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  expect(compiled.chords).toEqual(partialScore.chords);expect(compiled.beats).toEqual([]);
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  expect(writes).toBe(0);
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await expect(preview).toHaveCount(0);
  await page.getByRole('button',{name:'編輯 0.00 秒的 C',exact:true}).click();
  expect(Number(await page.getByLabel('結束時間（秒）',{exact:true}).inputValue())).toBe(12);
  await page.getByLabel('和弦名稱',{exact:true}).fill('Em');
  await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  await page.getByRole('button',{name:'完成編輯',exact:true}).click();
  await expect(preview.getByRole('button',{name:'播放 4.00 秒的 Em',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(preview.getByRole('button',{name:'播放 4.00 秒的 C',exact:true})).toBeVisible();
});

for(const variant of ['missing','wrong-source','wrong-crop'])test(`unavailable or mismatched timing preview preserves time sheet (${variant})`,async({page})=>{
  await page.route('**/timing-preview',r=>variant==='missing'?r.fulfill({status:404}):r.fulfill({json:{...partialPreview,...(variant==='wrong-source'?{job_id:'other'}:{source_start_seconds:40})}}));
  await setup(page,partialScore);
  await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await expect(page.getByLabel(/預覽可辨識的小節/)).toHaveCount(0);
  await expect(page.locator('.notation-measure')).toHaveCount(0);
});

test('unmetered sheet edits seconds, adjacent boundary, undo, delete and autosave without fake bars',async({page})=>{
  await setup(page,timelineScore);
  await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await expect(page.getByText('這首歌的小節位置尚未確認，先顯示和弦時間表。每列是一段和弦，不是一小節；目前每段彈一次。',{exact:true})).toBeVisible();
  await expect(page.locator('.notation-measure')).toHaveCount(0);
  await page.getByText('下載與備份',{exact:true}).click();
  await expect(page.getByRole('button',{name:'下載伴奏 MIDI',exact:true})).toBeHidden();
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 0.00 秒的 C',exact:true}).click();
  await expect(page.getByRole('button',{name:'增加半拍'})).toHaveCount(0);
  let saved:any;await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'timeline-save'}})});
  await page.getByLabel('結束時間（秒）',{exact:true}).fill('4.125');
  await page.getByRole('button',{name:'套用時間',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 4.13 秒的 G',exact:true})).toBeVisible();
  await expect.poll(()=>saved?.score?.chords?.[1].start).toBe(4.125);
  expect(saved.score.chords[0].end).toBe(4.125);
  expect(saved.score.analysis.timing_status).toBe('unmetered');expect(saved.score.beats).toEqual([]);
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByRole('button',{name:'編輯 3.22 秒的 G',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'編輯 3.22 秒的 G',exact:true}).click();
  await page.getByRole('button',{name:'刪除此段和弦',exact:true}).click();
  await expect(page.getByLabel('和弦時間表',{exact:true}).getByRole('button')).toHaveCount(1);
  await expect.poll(()=>saved?.score?.chords?.length).toBe(1);
  expect(saved.score.chords[0].end).toBe(3.217);
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByLabel('和弦時間表',{exact:true}).getByRole('button')).toHaveCount(2);
});

for(const width of [320,390,1440])test(`unmetered timeline has no overflow at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:844});await setup(page,timelineScore);
  await expect(page.getByLabel('歌曲調性')).toBeVisible();await expect(page.getByLabel('歌曲 Capo')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await expect(page.getByText('這首歌的小節位置尚未確認',{exact:false})).toBeVisible();
  const rowBounds=await page.getByLabel('和弦時間表',{exact:true}).getByRole('button').evaluateAll(els=>els.map(el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width}}));
  expect(rowBounds[1].y).toBeGreaterThan(rowBounds[0].y);
  expect(rowBounds[1].x).toBe(rowBounds[0].x);
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByLabel('循環選取時間').check();
  await page.getByLabel('到（秒）').fill('0');
  await expect(page.getByRole('alert')).toContainText('結束須晚於開始');
  await expect(page.getByRole('button',{name:'播放',exact:true})).toBeDisabled();
  await page.screenshot({path:`test-results/chord-timeline-${width}.png`,fullPage:true});
});

test('fresh installation opens portable example without a local job and offers source analysis',async({page})=>{
  const example={...timelineScore,song:{...timelineScore.song,title:'小手拉大手 · 範例和弦稿',source_type:'example',source_url:'https://www.youtube.com/watch?v=5wq_uTMW0v8'},provenance:{...score.provenance,parameters:{example_id:'little-hands'}}};
  await page.route('**/api/v1/capabilities',r=>r.fulfill({json:{melody_available:false,youtube_enabled:true}}));
  await page.route('**/examples/little-hands',r=>r.fulfill({json:example}));
  let saved:any;
  await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'new-example'}})});
  await page.route('**/revisions/*/history',r=>r.fulfill({json:[]}));
  await page.route('**/rhythm-patterns?*',r=>r.fulfill({json:[]}));
  await page.goto('/');
  await page.getByRole('button',{name:'開啟範例：小手拉大手',exact:true}).click();
  await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await expect(page.getByLabel('播放聲音',{exact:true})).toHaveValue('guitar');
  await expect(page.getByRole('button',{name:'播放',exact:true})).toBeEnabled();
  await expect(page).toHaveURL(/revision=new-example/);
  expect(saved.score.song.source_type).toBe('example');
  await page.getByRole('button',{name:'用這首歌曲開始分析',exact:true}).click();
  await expect(page.getByLabel('YouTube video URL')).toHaveValue(example.song.source_url);
  await expect(page.getByLabel('Analysis duration')).toHaveValue('full');
  await expect(page.getByRole('button',{name:'Start analysis',exact:true})).toBeEnabled();
});

test('follow-along shows current and next chords and scrolling can be disabled',async({page})=>{
  const working={...timelineScore,song:{...timelineScore.song,duration_seconds:60},chords:Array.from({length:30},(_,i)=>({...score.chords[0],id:'c'+i,start:i*2,end:(i+1)*2,symbol:i%2?'G':'C'}))};
  await page.setViewportSize({width:390,height:700});await setup(page,working);
  await page.route('**/scores/playback/manifest',r=>r.fulfill({json:{revision:'follow',duration_seconds:60,bpm:0,time_signature:'',events:working.chords.map(c=>({id:c.id,track:'guitar',start:c.start,end:c.end,sustain_end:c.end,pitches:[48],pitch_offsets:[0],pitch_velocities:[98],velocity:98,source_id:c.id}))}}));
  await page.getByLabel('播放聲音',{exact:true}).selectOption('guitar');
  await page.getByRole('button',{name:'播放 40.00 秒的 C',exact:true}).click();
  await expect(page.getByLabel('跟彈提示',{exact:true})).toContainText('目前 C');
  await expect(page.getByLabel('跟彈提示',{exact:true})).toContainText('接著 G');
  const bounds=await page.locator('[data-chord-id="c20"]').boundingBox();expect(bounds!.y).toBeGreaterThan(0);expect(bounds!.y+bounds!.height).toBeLessThan(700);
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByLabel('跟隨播放位置',{exact:true}).uncheck();
  await expect(page.getByLabel('跟隨播放位置',{exact:true})).not.toBeChecked();
});

test('performance draft updates shared timing, autosaves, and restores with undo',async({page})=>{
  const working={...score,chords:[{...score.chords[0],end:2.019},{...score.chords[0],id:'g',symbol:'G',start:2.019,end:8}]};
  await setup(page,working);
  let saved:any;
  await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'performance-saved'}})});
  await page.route('**/scores/performance-draft',r=>{
    const original=r.request().postDataJSON();
    return r.fulfill({json:{score:{...original,chords:[{...original.chords[0],end:2},{...original.chords[1],start:2}],provenance:{...original.provenance,parameters:{...original.provenance.parameters,chord_grid_candidate:'nearest-eighth-v1',performance_draft:'preserve-harmony-v1'}}},report:{}}});
  });
  await expect(page.getByLabel('Bar 2',{exact:true}).getByRole('button')).toHaveCount(2);
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'整理演奏稿',exact:true}).click();
  await expect(page.getByLabel('Bar 2',{exact:true}).getByRole('button')).toHaveCount(1);
  await expect.poll(()=>saved?.score?.chords[1].start).toBe(2);
  expect(saved.score.provenance.parameters.analysis_source_job_id).toBe('product-job');
  expect(saved.score.melody).toHaveLength(1);
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByLabel('Bar 2',{exact:true}).getByRole('button')).toHaveCount(2);
  await expect.poll(()=>saved?.score?.chords[1].start).toBe(2.019);
});

test('bar strums use the saved score rhythm and can undo and redo without changing harmony',async({page})=>{
  await setup(page);
  let saved:any;
  await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'bar-strums'}})});
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'每小節一下',exact:true}).click();
  await expect.poll(()=>saved?.score?.rhythm?.pattern_id).toBe('observed-downbeats-v1');
  expect(saved.score.chords).toEqual(score.chords);
  expect(saved.score.beats).toEqual(score.beats);
  expect(saved.score.melody).toHaveLength(1);
  await expect(page.getByRole('button',{name:'已選：每小節一下',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect.poll(()=>saved?.score?.rhythm?.pattern_id).toBe(score.rhythm.pattern_id);
  await page.getByRole('button',{name:'重做',exact:true}).click();
  await expect.poll(()=>saved?.score?.rhythm?.pattern_id).toBe('observed-downbeats-v1');
  let exported:any;
  await page.route('**/scores/midi',r=>{exported=r.request().postDataJSON();return r.fulfill({body:'midi',contentType:'audio/midi'});});
  await page.getByText('下載與備份',{exact:true}).click();
  await page.getByRole('button',{name:'下載伴奏 MIDI',exact:true}).click();
  await expect.poll(()=>exported?.rhythm?.pattern_id).toBe('observed-downbeats-v1');
});

test('unmetered timeline cannot promise a bar-based strum',async({page})=>{
  await setup(page,timelineScore);
  await page.getByText('練習與編輯',{exact:true}).click();
  await expect(page.getByRole('button',{name:'每小節一下',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'每拍一下',exact:true})).toHaveCount(0);
});

test('every-beat strums preserve harmony and beats through save, undo, redo and export',async({page})=>{
  await setup(page);let saved:any,exported:any;
  await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'beat-strums'}})});
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'每拍一下',exact:true}).click();
  await expect.poll(()=>saved?.score?.rhythm?.pattern_id).toBe('observed-quarter-beats-v1');
  expect(saved.score.chords).toEqual(score.chords);expect(saved.score.beats).toEqual(score.beats);
  expect(saved.score.rhythm.accents).toEqual([1,.7,.7,.7]);
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect.poll(()=>saved?.score?.rhythm?.pattern_id).toBe(score.rhythm.pattern_id);
  await page.getByRole('button',{name:'重做',exact:true}).click();
  await expect(page.getByRole('button',{name:'已選：每拍一下',exact:true})).toBeDisabled();
  await page.route('**/scores/midi',r=>{exported=r.request().postDataJSON();return r.fulfill({body:'midi',contentType:'audio/midi'})});
  await page.getByText('下載與備份',{exact:true}).click();
  await page.getByRole('button',{name:'下載伴奏 MIDI',exact:true}).click();
  await expect.poll(()=>exported?.rhythm?.pattern_id).toBe('observed-quarter-beats-v1');
  expect(exported.chords).toEqual(score.chords);expect(exported.beats).toEqual(score.beats);
});

test('a delayed performance draft cannot overwrite a newer manual chord edit',async({page})=>{
  await setup(page,timelineScore);
  let release:()=>void=()=>{};const ready=new Promise<void>(resolve=>{release=resolve;});
  let submitted=false;
  await page.route('**/scores/performance-draft',async r=>{
    submitted=true;const original=r.request().postDataJSON();await ready;
    await r.fulfill({json:{score:{...original,chords:original.chords.map(c=>({...c,symbol:'F#'}))},report:{}}}).catch(()=>{});
  });
  let saved:any;await page.route('**/revisions',r=>{saved=r.request().postDataJSON();return r.fulfill({json:{revision_id:'manual-kept'}})});
  await page.getByText('練習與編輯',{exact:true}).click();
  await page.getByRole('button',{name:'整理演奏稿',exact:true}).click();await expect.poll(()=>submitted).toBe(true);
  await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 0.00 秒的 C',exact:true}).click();
  await page.getByLabel('和弦名稱',{exact:true}).fill('Em');
  await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  release();
  await expect(page.getByRole('button',{name:'編輯 0.00 秒的 Em',exact:true})).toBeVisible();
  await expect.poll(()=>saved?.score?.chords[0].symbol).toBe('Em');
  expect(saved.score.provenance.parameters.performance_draft).toBeUndefined();
});
