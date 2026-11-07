import {markLyric,undoLyricMark} from '../src/lyricMarking';
import {createReviewTransportClock} from '../src/transportClock';
import {readFileSync} from "node:fs";
const acceptedGrid=JSON.parse(readFileSync(new URL("./fixtures/accepted-chord-grid.json",import.meta.url),"utf8"));
import {anchorStatus,fullNotePositions,localNotePositions,notesInRange,readingBars} from '../src/songNoteTimeline';
import {newLine} from '../src/worksheetDocument';
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
function sourceWav(seconds=8){
  const sr=8000,bytes=sr*seconds*2,buffer=Buffer.alloc(44+bytes);
  buffer.write('RIFF',0);buffer.writeUInt32LE(36+bytes,4);buffer.write('WAVEfmt ',8);buffer.writeUInt32LE(16,16);
  buffer.writeUInt16LE(1,20);buffer.writeUInt16LE(1,22);buffer.writeUInt32LE(sr,24);buffer.writeUInt32LE(sr*2,28);
  buffer.writeUInt16LE(2,32);buffer.writeUInt16LE(16,34);buffer.write('data',36);buffer.writeUInt32LE(bytes,40);
  return buffer;
}
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
  await expect(page.getByLabel('播放聲音',{exact:true})).toHaveValue(originalSource?'source':'mix');
  await expect(page.getByRole('button',{name:'播放',exact:true})).toBeEnabled();
  await expect(page.getByText('原曲維持原調；吉他使用目前和弦，可能不同調，供聽感核對。',{exact:true})).toBeVisible();
  await expect(page.getByLabel('播放聲音').locator('option[value=mix]')).not.toHaveAttribute('disabled');
  if(!originalSource){
    await page.route('**/api/v1/jobs/product-job/audio',r=>r.fulfill({body:sourceWav(),contentType:'audio/wav'}));
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

async function setup(page:any, working:any=score, timingView?:string,entryPath='/') {
  await page.addInitScript(()=>{localStorage.setItem('guitarscribe.editorView','melody');localStorage.setItem('guitarscribe.workspaceMode','full');});
  await page.route('**/api/v1/capabilities',r=>r.fulfill({json:{melody_available:true,youtube_enabled:true,vocal_separation_enabled:true}}));
  const archived={...working,melody:[{id:'n',start:0,end:1,midi:60,note:'C4',confidence:1,origin:'model',edited:false}]};
  await page.route('**/api/v1/jobs/product-job',r=>r.fulfill({json:{id:'product-job',status:'completed',progress:100,artifacts:[],score:archived}}));
  await page.route('**/api/v1/jobs/product-job/audio',r=>r.fulfill({status:404,body:''}));
  await page.route('**/revisions/*/history',r=>r.fulfill({json:[]}));
  await page.route('**/revisions',r=>r.fulfill({json:{revision_id:'auto-saved'}}));
  await page.route('**/rhythm-patterns?*',r=>r.fulfill({json:[]}));
  await page.goto(entryPath+'?job=product-job&view=melody'+(timingView?`&timingView=${timingView}`:''));
  await expect(page.getByRole('region',{name:'和弦核對'})).toBeVisible({timeout:15000});
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

test('text melody notes autosave separately and survive reload, chord Undo and original restore',async({page})=>{
  let note={job_id:'product-job',text:'',version:0},writes=0;
  await page.route('**/melody-notes',r=>{
    if(r.request().method()==='GET')return r.fulfill({json:note});
    const body=r.request().postDataJSON();expect(body.expected_version).toBe(note.version);note={...note,text:body.text,version:note.version+1};return r.fulfill({json:note});
  });
  await setup(page,partialScore);await openLegacyNotes(page);
  await page.route('**/revisions',r=>{writes++;return r.fulfill({json:{revision_id:'notes-control'}});});
  await page.getByLabel('旋律筆記',{exact:true}).fill('自己抓G大調\n旋律 5 6 1');
  await expect.poll(()=>note.text).toBe('自己抓G大調\n旋律 5 6 1');
  await expect(page.getByLabel('筆記保存狀態')).toHaveText('已保存');expect(writes).toBe(0);
  await page.reload();await openLegacyNotes(page);
  await expect(page.getByLabel('旋律筆記',{exact:true})).toHaveValue(note.text);
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'編輯和弦',exact:true}).click();
  await page.getByRole('button',{name:'編輯 0.00 秒的 C',exact:true}).click();
  await page.getByLabel('和弦名稱',{exact:true}).fill('Em');await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();
  await page.getByRole('button',{name:'復原',exact:true}).click();
  await expect(page.getByLabel('旋律筆記',{exact:true})).toHaveValue(note.text);
  await page.getByText('版本歷史與還原',{exact:true}).click();page.once('dialog',d=>d.accept());
  await page.getByRole('button',{name:'還原原始分析',exact:true}).click();
  await expect(page.getByLabel('旋律筆記',{exact:true})).toHaveValue('自己抓G大調\n旋律 5 6 1');
});

test('per-tab offline melody draft survives another tab saving and repeated conflict reloads',async({context,page})=>{
  let note={job_id:'product-job',text:'',version:0},offline=true;
  await context.route('**/melody-notes',async r=>{
    if(r.request().method()==='GET'){await r.fulfill({json:note}).catch(()=>{});return;}
    if(offline&&r.request().frame().page()===page){await r.abort();return;}
    const body=r.request().postDataJSON();
    if(body.expected_version!==note.version){await r.fulfill({status:409});return;}
    note={...note,text:body.text,version:note.version+1};await r.fulfill({json:note});
  });
  const other=await context.newPage();await setup(page,partialScore);await setup(other,partialScore);
  await openLegacyNotes(page);await openLegacyNotes(other);
  await page.getByLabel('旋律筆記',{exact:true}).fill('A分頁離線手記');
  await expect(page.getByLabel('筆記保存狀態')).toContainText('保存失敗，文字仍保留');
  await other.getByLabel('旋律筆記',{exact:true}).fill('B分頁已保存');
  await expect.poll(()=>note.text).toBe('B分頁已保存');
  offline=false;
  for(let i=0;i<2;i++){
    await page.reload();await openLegacyNotes(page);
    await expect(page.getByLabel('旋律筆記',{exact:true})).toHaveValue('A分頁離線手記');
    await expect(page.getByLabel('筆記保存狀態')).toContainText('其他瀏覽器已更新');
    expect(note.text).toBe('B分頁已保存');
  }
  page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'載入最新筆記',exact:true}).click();
  await expect(page.getByLabel('旋律筆記',{exact:true})).toHaveValue('B分頁已保存');
  await other.close();
});

test('failed note loading retains a recoverable per-tab draft and uses plain language',async({page})=>{
  await page.addInitScript(()=>sessionStorage.setItem('guitarscribe.melodyNoteDraft.product-job',JSON.stringify({text:'先記G調，尚未存',baseVersion:0})));
  await page.route('**/melody-notes',r=>r.abort());await setup(page,partialScore);
  await openLegacyNotes(page);
  await expect(page.getByLabel('旋律筆記',{exact:true})).toHaveValue('先記G調，尚未存');
  await expect(page.getByLabel('筆記保存狀態')).toContainText('筆記暫時無法載入');
});

for(const width of [320,390,1440])test(`automatic local reading candidate starts in draft and preserves source editing (${width})`,async({page})=>{
  await page.setViewportSize({width,height:844});
  await page.route('**/timing-preview',r=>r.fulfill({json:partialPreview}));
  await setup(page,partialScore,'auto');
  const preview=page.getByLabel('局部小節預覽',{exact:true});
  await expect(preview).toBeVisible();
  await expect(preview.locator('.notation-measure')).toHaveCount(4);
  await expect(preview.locator('.partial-unknown')).toHaveCount(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:'時間明細',exact:true}).click();
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
  await expect(page.getByLabel('連續和弦讀譜',{exact:true})).toBeVisible();
  await expect(page.getByLabel('讀譜方式',{exact:true})).toBeVisible();
  await expect(page.locator('.notation-measure')).toHaveCount(0);
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
  if(metered){await expect(page.getByLabel('讀譜方式',{exact:true})).toHaveCount(0);await expect(page.locator('.notation-measure')).toHaveCount(4);}
  else {await expect(page.getByLabel('連續和弦讀譜',{exact:true})).toBeVisible();await expect(page.locator('.notation-measure')).toHaveCount(0);}
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
  await expect(page.getByText('這首歌的小節位置尚未確認，先顯示和弦時間表。每列是一段和弦，不是一小節；撥奏依播放器選項。',{exact:true})).toBeVisible();
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


test('audition controls preserve score and live gains do not restart mixed playback',async({page})=>{
  await page.addInitScript(()=>{
    const Original=window.AudioContext;const probe={stops:0,starts:[] as Array<{duration:number;rate:number}>,targets:[] as number[]};
    (window as any).__auditionProbe=probe;
    class TrackedContext extends Original{
      createGain(){const node=super.createGain();const original=node.gain.setTargetAtTime.bind(node.gain);node.gain.setTargetAtTime=(value,time,constant)=>{probe.targets.push(value);return original(value,time,constant);};return node;}
      createBufferSource(){const node=super.createBufferSource(),start=node.start.bind(node),stop=node.stop.bind(node);
        node.start=((...args:any[])=>{probe.starts.push({duration:node.buffer?.duration??0,rate:node.playbackRate.value});(start as any)(...args);}) as typeof node.start;
        node.stop=((...args:any[])=>{probe.stops++;(stop as any)(...args);}) as typeof node.stop;return node;}
    }
    window.AudioContext=TrackedContext;
  });
  await setup(page,{...score,song:{...score.song,duration_seconds:60},chords:[{...score.chords[0],end:60}]});await page.route('**/api/v1/jobs/product-job/audio',r=>r.fulfill({body:sourceWav(60),contentType:'audio/wav'}));
  let compiles=0,body:any,query:any;
  await page.route('**/scores/audition-playback?*',r=>{compiles++;body=r.request().postDataJSON();query=new URL(r.request().url()).searchParams;return r.fulfill({json:{revision:'audition',duration_seconds:60,bpm:120,time_signature:'4/4',events:[{id:'g',track:'guitar',start:0,end:60,sustain_end:60,pitches:[48],pitch_offsets:[0],pitch_velocities:[98],velocity:98,source_id:'c'}]}});});
  await expect(page.getByLabel('撥奏內容')).toHaveValue('chord');await expect(page.getByLabel('撥奏頻率')).toHaveValue('original');
  await page.getByLabel('撥奏內容').selectOption('root');await page.getByLabel('撥奏頻率').selectOption('two');
  await page.getByRole('button',{name:'播放',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  expect(query.get('content')).toBe('root');expect(query.get('pulse')).toBe('two');expect(body.chords[0].symbol).toBe('C');
  const before=await page.evaluate(()=>(window as any).__auditionProbe.stops);
  for(const [name,value] of [['原曲音量','0.11'],['和弦／根音音量','0'],['和弦／根音音量','0.71']]){
    await page.getByLabel(name,{exact:true}).fill(value);await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  }
  const probe=await page.evaluate(()=>(window as any).__auditionProbe);
  expect(probe.stops).toBe(before);expect(compiles).toBe(1);expect(probe.targets).toEqual(expect.arrayContaining([.11,0,.71]));
  expect(probe.starts.some((s:any)=>s.duration===60&&s.rate===1)).toBe(true);
  await expect(page.getByLabel('跟彈提示')).toContainText('目前 C');await expect(page.locator('.notation-sheet button.current-chord')).toHaveCount(1);
  for(const [width,height] of [[320,844],[390,844],[844,390]]){
    await page.setViewportSize({width,height});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const rect=await page.locator('.timeline-transport').boundingBox();expect(rect!.height).toBeLessThan(height*.65);
  }
  await page.getByRole('button',{name:'暫停',exact:true}).click();
});

for(const available of [false,true])test(`partial pulse options reflect observed preview availability (${available})`,async({page})=>{
  await page.route('**/timing-preview',r=>r.fulfill({json:available?partialPreview:{...partialPreview,covered_seconds:0,regions:[]}}));await setup(page,partialScore,'auto');
  const option=page.getByLabel('撥奏頻率').locator('option[value=one]');
  if(available){
    await expect(option).not.toHaveAttribute('disabled');await page.getByLabel('撥奏頻率').selectOption('half');
    await expect(page.getByText('依待確認拍點試聽；未知段暫停伴奏，原曲繼續。這些選項不更改樂譜。',{exact:true})).toBeVisible();
  }else{await expect(option).toHaveAttribute('disabled','');await expect(page.getByLabel('撥奏內容')).toBeEnabled();}
});


test('candidate without query reads every chord naturally and preserves unlabelled gaps and explicit rests',async({page})=>{
  const working={...timelineScore,song:{...timelineScore.song,duration_seconds:8},chords:[
    {...score.chords[0],id:'one',start:.5,end:1.1}, {...score.chords[0],id:'repeat',start:1.1,end:1.15},
    {...score.chords[0],id:'rest',symbol:'N',start:2,end:2.5}, {...score.chords[0],id:'slash',symbol:'G7/B',start:3,end:7},
  ]};
  await page.route('**/timing-preview',r=>r.fulfill({status:404}));
  await setup(page,working,undefined,'/reading-candidate-2026-11-05/');
  const reading=page.getByLabel('連續和弦讀譜',{exact:true});await expect(reading).toBeVisible();
  await expect(reading.locator('button[data-chord-id]')).toHaveCount(4);await expect(reading.locator('button[data-gap]')).toHaveCount(4);
  await expect(reading.locator('button[data-chord-id=repeat]')).toHaveAttribute('title','1.100–1.150 秒 · C');
  await expect(reading.getByText('C',{exact:true})).toHaveCount(2);await expect(reading.getByText('N · 休止',{exact:true})).toBeVisible();
  await expect(reading.getByText('G7/B',{exact:true})).toBeVisible();await expect(page.locator('.notation-measure')).toHaveCount(0);
  for(const width of [320,390,1440]){await page.setViewportSize({width,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
  let compileCount=0,compiled:any;
  await page.route('**/scores/playback/manifest',r=>{compileCount++;compiled=r.request().postDataJSON();return r.fulfill({json:{revision:'unchanged',duration_seconds:8,bpm:0,time_signature:'',events:[{id:'g',track:'guitar',start:0,end:8,sustain_end:8,pitches:[48],pitch_offsets:[0],pitch_velocities:[98],velocity:98,source_id:'one'}]}});});
  await page.getByLabel('播放聲音').selectOption('guitar');
  await reading.getByRole('button',{name:'播放 0.50 秒的 C',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();
  expect(compiled.chords).toEqual(working.chords);
  await page.getByRole('button',{name:'時間明細',exact:true}).click();await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();expect(compileCount).toBe(1);
  await page.getByRole('button',{name:'連續和弦 · 待確認',exact:true}).click();await expect(reading).toBeVisible();expect(compileCount).toBe(1);
  await page.getByRole('button',{name:'暫停',exact:true}).click();
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'到時間表編輯',exact:true}).click();
  await expect(reading).toHaveCount(0);await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'完成編輯',exact:true}).click();await expect(reading).toBeVisible();
});

for(const view of ['time','table'])test(`candidate respects explicit ${view} and restores that choice after editing`,async({page})=>{
  await page.route('**/timing-preview',r=>r.fulfill({status:404}));await setup(page,timelineScore,view,'/reading-candidate-2026-11-05/');
  await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();await expect(page.getByLabel('連續和弦讀譜',{exact:true})).toHaveCount(0);
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:'到時間表編輯',exact:true}).click();
  await page.getByRole('button',{name:'完成編輯',exact:true}).click();await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
});

test('a late preview cannot override an explicit time-detail choice on the candidate',async({page})=>{
  let release!:()=>void;const held=new Promise<void>(r=>{release=r});
  await page.route('**/timing-preview',async r=>{await held;await r.fulfill({json:partialPreview}).catch(()=>{});});
  try{
    await setup(page,partialScore,undefined,'/reading-candidate-2026-11-05/');await expect(page.getByLabel('連續和弦讀譜',{exact:true})).toBeVisible();
    await page.getByRole('button',{name:'時間明細',exact:true}).click();release();
    await expect(page.getByRole('button',{name:'局部譜 · 待確認',exact:true})).toBeVisible();await expect(page.getByLabel('和弦時間表',{exact:true})).toBeVisible();
    await expect(page.getByLabel('局部小節預覽',{exact:true})).toHaveCount(0);
    await page.getByRole('button',{name:'局部譜 · 待確認',exact:true}).click();await expect(page.getByLabel('局部小節預覽',{exact:true})).toBeVisible();
  }finally{release();}
});

// A22: independent lyric worksheet, never a mutation of the analysed score.
const emptySheet=()=>({job_id:'product-job',document:{source:'',lines:[] as any[]},version:0});
async function openWorksheet(page:any){if(await page.locator('.lyric-worksheet').getAttribute('open')===null)await page.getByText('歌曲筆記（歌詞與簡譜）',{exact:true}).click();await expect(page.getByLabel('歌詞工作頁保存狀態')).not.toContainText('正在載入');}
async function pasteWorksheet(page:any,text:string){await quickLyrics(page,text);}
for(const width of [320,1440])test(`lyric worksheet preserves repeated lines, notation, IDs and original notes (${width})`,async({page})=>{
  await page.setViewportSize({width,height:844});let sheet=emptySheet(),writes=0,notes=0;
  await page.route('**/lyric-worksheet',r=>{if(r.request().method()==='GET')return r.fulfill({json:sheet});const body=r.request().postDataJSON();expect(body.expected_version).toBe(sheet.version);sheet={...sheet,document:body.document,version:sheet.version+1};return r.fulfill({json:sheet});});
  await page.route('**/melody-notes',r=>{if(r.request().method()!=='GET')notes++;return r.fulfill({json:{job_id:'product-job',text:'既有手記',version:1}});});
  await setup(page,partialScore);await page.route('**/revisions',r=>{writes++;return r.fulfill({json:{revision_id:'unexpected'}})});await openWorksheet(page);
  await pasteWorksheet(page,'副歌  一\n\n副歌  一');await page.getByLabel('簡譜第1行',{exact:true}).fill(" 5  0 - #1' ");
  await expect.poll(()=>sheet.document.lines[0]?.notation).toBe(" 5  0 - #1' ");const id=sheet.document.lines[0].id;
  expect(sheet.document.lines.map(r=>r.lyric)).toEqual(['副歌  一','','副歌  一']);
  await revealNotes(page,'微調位置／文字行');await page.getByRole('button',{name:'在第1行下方新增',exact:true}).click();await expect(page.getByLabel('歌曲筆記安排')).toContainText('4. 副歌  一');await revealNotes(page,'選擇其他句／完整安排');await page.getByLabel('歌曲筆記安排').getByRole('button').first().click();
  expect(await page.locator('.worksheet-line').first().getAttribute('data-line-id')).toBe(id);
  page.once('dialog',d=>d.dismiss());await revealNotes(page,'微調位置／文字行');await page.getByRole('button',{name:'移除第1行',exact:true}).click();await expect(page.getByLabel('簡譜第1行',{exact:true})).toHaveValue(" 5  0 - #1' ");
  await expect(page.getByLabel('歌詞工作頁保存狀態')).toHaveText('已保存');await page.reload();await openWorksheet(page);await revealNotes(page,'選擇其他句／完整安排');await page.getByLabel('歌曲筆記安排').getByRole('button').first().click();
  await expect(page.getByLabel('簡譜第1行',{exact:true})).toHaveValue(" 5  0 - #1' ");await openLegacyNotes(page);await expect(page.getByLabel('旋律筆記',{exact:true})).toHaveValue('既有手記');
  expect(writes).toBe(0);expect(notes).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('lyric worksheet conflict keeps offline draft across repeated reloads',async({context,page})=>{
  let sheet=emptySheet(),offline=true;
  await context.route('**/lyric-worksheet',async r=>{
    if(r.request().method()==='GET'){await r.fulfill({json:sheet}).catch(()=>{});return;}
    if(offline&&r.request().frame().page()===page){await r.abort();return;}
    const body=r.request().postDataJSON();if(body.expected_version!==sheet.version){await r.fulfill({status:409});return;}
    sheet={...sheet,document:body.document,version:sheet.version+1};await r.fulfill({json:sheet});
  });
  const other=await context.newPage();await setup(page,partialScore);await setup(other,partialScore);await openWorksheet(page);await openWorksheet(other);
  await pasteWorksheet(page,'A離線草稿');await expect(page.getByLabel('歌詞工作頁保存狀態')).toContainText('保存失敗');
  await pasteWorksheet(other,'B已保存');await expect.poll(()=>sheet.document.lines[0]?.lyric).toBe('B已保存');offline=false;
  for(let i=0;i<2;i++){await page.reload();await openWorksheet(page);await revealNotes(page,'選擇其他句／完整安排');await page.getByLabel('歌曲筆記安排').getByRole('button').first().click();await expect(page.getByLabel('歌詞第1行',{exact:true})).toHaveValue('A離線草稿');await expect(page.getByLabel('歌詞工作頁保存狀態')).toContainText('其他瀏覽器已更新');expect(sheet.document.lines[0].lyric).toBe('B已保存');}
  page.once('dialog',d=>d.accept());await revealNotes(page,'來源／備份／舊筆記');await page.getByRole('button',{name:'載入最新歌詞工作頁',exact:true}).click();await revealNotes(page,'選擇其他句／完整安排');await page.getByLabel('歌曲筆記安排').getByRole('button').first().click();await expect(page.getByLabel('歌詞第1行',{exact:true})).toHaveValue('B已保存');await other.close();
});

for(const raw of ['{bad-json',JSON.stringify({text:'{bad-inner',baseVersion:0})])test(`lyric worksheet corrupt draft supports backup and confirmed recovery (${raw.length})`,async({page})=>{
  let puts=0;await page.addInitScript(raw=>sessionStorage.setItem('guitarscribe.lyricWorksheetDraft.product-job',raw),raw);
  await page.route('**/lyric-worksheet',r=>{if(r.request().method()==='PUT')puts++;return r.fulfill({json:{...emptySheet(),version:2,document:{source:'server',lines:[{id:'saved',lyric:'伺服器版本',notation:'1 2',start:null,end:null}]}}});});
  await setup(page,partialScore);await openWorksheet(page);await expect(page.getByLabel('歌詞工作頁保存狀態')).toContainText('草稿格式無法讀取');
  const download=page.waitForEvent('download');await revealNotes(page,'來源／備份／舊筆記');await page.getByRole('button',{name:'下載工作頁備份',exact:true}).click();const file=await (await download).path();expect(readFileSync(file!,'utf8')).toBe(raw);
  page.once('dialog',d=>d.dismiss());await revealNotes(page,'來源／備份／舊筆記');await page.getByRole('button',{name:'載入最新歌詞工作頁',exact:true}).click();await expect(page.getByLabel('歌詞第1行',{exact:true})).toHaveCount(0);
  page.once('dialog',d=>d.accept());await revealNotes(page,'來源／備份／舊筆記');await page.getByRole('button',{name:'載入最新歌詞工作頁',exact:true}).click();await revealNotes(page,'選擇其他句／完整安排');await page.getByLabel('歌曲筆記安排').getByRole('button').first().click();await expect(page.getByLabel('歌詞第1行',{exact:true})).toHaveValue('伺服器版本');expect(puts).toBe(0);
});

test('lyric worksheet explicitly previews foreign captions, cancels stale result and preserves LRC repeats',async({page})=>{
  let sheet=emptySheet(),previews=0;
  await page.route('**/lyric-worksheet',r=>{if(r.request().method()==='GET')return r.fulfill({json:sheet});const body=r.request().postDataJSON();sheet={...sheet,document:body.document,version:sheet.version+1};return r.fulfill({json:sheet});});
  await page.route('**/lyric-caption-tracks',r=>r.fulfill({json:{job_id:'product-job',tracks:[{id:'manual:es',language:'es',kind:'manual',name:'Spanish'},{id:'automatic:ko-orig',language:'ko-orig',kind:'automatic',name:'Korean'}]}}));
  let resolve!:()=>void;const gate=new Promise<void>(r=>resolve=r);
  await page.route('**/lyric-caption-preview',async r=>{previews++;await gate;await r.fulfill({json:{job_id:'product-job',track:{id:'manual:es',language:'es',kind:'manual',name:'Spanish'},lines:[{lyric:'foreign draft',start:null,end:null}],message:'draft'}}).catch(()=>{});});
  await setup(page,{...partialScore,song:{...partialScore.song,source_type:'youtube'}});await openWorksheet(page);
  await revealNotes(page,'其他匯入方式／字幕初稿');await page.getByRole('button',{name:'取得影片字幕初稿',exact:true}).click();await expect(page.getByLabel('字幕語言',{exact:true})).toHaveValue('');await expect(page.getByRole('button',{name:'預覽所選字幕',exact:true})).toBeDisabled();expect(previews).toBe(0);
  await page.getByLabel('字幕語言',{exact:true}).selectOption('manual:es');await page.getByRole('button',{name:'預覽所選字幕',exact:true}).click();await expect.poll(()=>previews).toBe(1);
  await revealNotes(page,'其他匯入方式／字幕初稿');await page.getByLabel('歌詞匯入格式',{exact:true}).selectOption('lrc');await page.getByLabel('貼上歌詞初稿').fill('[00:01][00:03]副歌\n[00:04]再唱');await page.getByRole('button',{name:'預覽貼上內容',exact:true}).click();resolve();
  await expect(page.getByLabel('歌詞初稿預覽')).toContainText('使用者LRC');await page.getByRole('button',{name:'加入空白工作頁',exact:true}).click();
  await expect.poll(()=>sheet.document.lines.length).toBe(3);expect(sheet.document.lines.map(r=>r.lyric)).toEqual(['副歌','副歌','再唱']);expect(sheet.document.lines.map(r=>[r.start,r.end])).toEqual([[1,null],[3,null],[4,null]]);
});


async function openLegacyNotes(page:any){
  const panel=page.locator('.lyric-worksheet');if(await panel.getAttribute('open')===null)await openWorksheet(page);
  await revealNotes(page,'來源／備份／舊筆記');const notes=page.locator('.melody-text-notes');if(await notes.getAttribute('open')===null)await page.getByText('未定位的舊筆記',{exact:true}).click();
}

test('song note timeline never invents bars, keeps half-open spans and flags frame/grid changes',()=>{
  const working=score as any,positions=fullNotePositions(working,readingBars(working));expect(positions).toHaveLength(4);
  expect(fullNotePositions({...working,beats:[]},readingBars({...working,beats:[]}))).toEqual([]);
  const row={...newLine('一句'),anchor:{time:2,end:6,source_start_seconds:0,duration_seconds:8,kind:'metered' as const,grid_id:positions[0].grid_id}};
  expect(notesInRange([row],working,0,2)).toEqual([]);expect(notesInRange([row],working,2,4)).toHaveLength(1);expect(notesInRange([row],working,4,6)).toHaveLength(1);expect(notesInRange([row],working,6,8)).toEqual([]);
  expect(anchorStatus(row.anchor,working,positions)).toBe('');expect(anchorStatus(row.anchor,working,[])).toContain('拍格已改變');
  const cropped={...working,song:{...working.song,source_start_seconds:10}};expect(notesInRange([row],cropped,0,8)).toEqual([]);expect(anchorStatus(row.anchor,cropped,positions)).toContain('來源時間範圍');
  const local=localNotePositions(partialPreview);expect(local).toHaveLength(4);expect(local[0].start).toBe(2);expect(local.at(-1)?.end).toBe(10);
});

for(const kind of ['metered','local','seconds'])for(const width of [320,1440])test(`song notes appear under chords, edit same row twice, play and persist (${kind},${width})`,async({page})=>{
  await page.setViewportSize({width,height:844});let sheet=emptySheet(),revisions=0;
  await page.route('**/lyric-worksheet',r=>{if(r.request().method()==='GET')return r.fulfill({json:sheet});const body=r.request().postDataJSON();expect(body.anchor_schema).toBe(1);sheet={...sheet,document:body.document,version:sheet.version+1};return r.fulfill({json:sheet});});
  if(kind==='local')await page.route('**/timing-preview',r=>r.fulfill({json:partialPreview}));else await page.route('**/timing-preview',r=>r.fulfill({status:404}));
  const working=kind==='metered'?score:kind==='local'?partialScore:timelineScore;
  await setup(page,working,'auto');await page.route('**/revisions',r=>{revisions++;return r.fulfill({json:{revision_id:'unexpected'}})});await openWorksheet(page);
  await pasteWorksheet(page,'一句跨小節');await page.getByLabel('簡譜第1行',{exact:true}).fill("5  6 1' - 0");
  if(kind==='seconds'){await revealNotes(page,'微調位置／文字行');await page.getByLabel('筆記開始秒數').fill('3.217');await revealNotes(page,'微調位置／文字行');await page.getByLabel('筆記結束秒數').fill('5');}
  else{await expect(page.getByLabel('筆記起始小節').locator('option')).toHaveCount(5);await revealNotes(page,'微調位置／文字行');await page.getByLabel('筆記起始小節').selectOption(kind==='metered'?'1':'0');await revealNotes(page,'微調位置／文字行');await page.getByLabel('筆記結束小節').selectOption(kind==='metered'?'2':'1');}
  await revealNotes(page,'微調位置／文字行');await page.getByRole('button',{name:'確認歌詞與簡譜位置',exact:true}).click();await expect.poll(()=>sheet.document.lines[0]?.anchor?.time).toBe(kind==='seconds'?3.217:2);
  const id=sheet.document.lines[0].id,inline=page.locator(`[data-note-id="${id}"]`).first();await expect(inline.locator('.located-lyric')).toHaveText('一句跨小節');await expect(inline.locator('.located-notation')).toHaveText("5  6 1' - 0");
  expect(await inline.evaluate(el=>!!el.closest('.notation-measure,.reading-piece'))).toBe(true);
  if(kind!=='seconds'){expect(await page.locator(`[data-note-id="${id}"]`).count()).toBe(2);await expect(page.locator(`[data-note-id="${id}"]`).nth(1)).toContainText('延續');}
  for(let i=0;i<2;i++){await page.getByRole('button',{name:'查看譜上位置',exact:true}).click();await expect(page.locator('.lyric-worksheet')).not.toHaveAttribute('open');await inline.getByRole('button',{name:'編輯第1組歌詞與簡譜',exact:true}).click();await expect(page.getByLabel('簡譜第1行',{exact:true})).toBeVisible();}
  await page.getByRole('button',{name:'查看譜上位置',exact:true}).click();await page.getByLabel('播放聲音',{exact:true}).selectOption('guitar');
  await page.route('**/scores/playback/manifest',r=>r.fulfill({json:{revision:'song-note',duration_seconds:working.song.duration_seconds,bpm:120,time_signature:'4/4',events:[{id:'g',track:'guitar',start:0,end:working.song.duration_seconds,sustain_end:working.song.duration_seconds,pitches:[48,52,55],pitch_offsets:[0,0,0],pitch_velocities:[98,98,98],velocity:98,source_id:'c'}]}}));
  await inline.getByRole('button',{name:'從第1組位置播放',exact:true}).click();await expect(page.getByRole('button',{name:'暫停',exact:true})).toBeVisible();await expect(page.locator('.playback-status')).not.toContainText('0.0 /');await inline.getByRole('button',{name:'編輯第1組歌詞與簡譜',exact:true}).click();await expect(page.getByRole('button',{name:'播放',exact:true})).toBeVisible();await expect(page.getByLabel('簡譜第1行',{exact:true})).toBeVisible();await page.getByRole('button',{name:'查看譜上位置',exact:true}).click();await page.screenshot({path:`../output/evaluation/song-notes-2026-11-07/${kind}-${width}.png`,fullPage:true});
  await page.reload();await expect(page.locator(`[data-note-id="${id}"]`).first().locator('.located-lyric')).toHaveText('一句跨小節');expect(sheet.document.lines).toHaveLength(1);expect(revisions).toBe(0);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('song notes use explicit caption confirmation, copy legacy without migration, and unlink without data loss',async({page})=>{
  let sheet=emptySheet(),noteWrites=0;
  await page.route('**/lyric-worksheet',r=>{if(r.request().method()==='GET')return r.fulfill({json:sheet});const body=r.request().postDataJSON();sheet={...sheet,document:body.document,version:sheet.version+1};return r.fulfill({json:sheet});});
  await page.route('**/melody-notes',r=>{if(r.request().method()!=='GET')noteWrites++;return r.fulfill({json:{job_id:'product-job',text:'原本整段筆記  5 6',version:1}});});
  await setup(page,timelineScore,'auto');await openWorksheet(page);await revealNotes(page,'其他匯入方式／字幕初稿');await page.getByLabel('歌詞匯入格式').selectOption('lrc');await pasteWorksheet(page,'[00:03]參考字幕');await expect(page.locator('[data-note-id]')).toHaveCount(0);
  await revealNotes(page,'微調位置／文字行');await page.getByRole('button',{name:'帶入來源參考時間（仍需確認）',exact:true}).click();await expect(page.locator('[data-note-id]')).toHaveCount(0);await revealNotes(page,'微調位置／文字行');await page.getByRole('button',{name:'確認歌詞與簡譜位置',exact:true}).click();await expect.poll(()=>sheet.document.lines[0]?.anchor?.time).toBe(3);
  await revealNotes(page,'微調位置／文字行');await page.getByRole('button',{name:'解除定位並保留文字',exact:true}).click();await expect.poll(()=>sheet.document.lines[0]?.anchor).toBeNull();await expect(page.getByLabel('歌詞第1行',{exact:true})).toHaveValue('參考字幕');
  await openLegacyNotes(page);await page.getByRole('button',{name:'複製選取文字或全文到未定位簡譜列（保留原文）',exact:true}).click();await expect(page.getByLabel('簡譜第2行',{exact:true})).toHaveValue('原本整段筆記  5 6');await expect(page.getByLabel('旋律筆記',{exact:true})).toHaveValue('原本整段筆記  5 6');expect(noteWrites).toBe(0);await expect.poll(()=>sheet.document.lines.length).toBe(2);expect(sheet.document.lines[1].anchor).toBeNull();
});


test('song notes re-confirm changed grid without moving time, and expose second-based fallback',async({page})=>{
  let sheet={...emptySheet(),version:1,document:{source:'old worksheet',lines:[{id:'retained',lyric:'原歌詞',notation:'5  6',start:null,end:null,anchor:{time:2,end:6,source_start_seconds:0,duration_seconds:8,kind:'metered',grid_id:'old-grid'}}]}};
  await page.route('**/lyric-worksheet',r=>{if(r.request().method()==='GET')return r.fulfill({json:sheet});const body=r.request().postDataJSON();sheet={...sheet,document:body.document,version:sheet.version+1};return r.fulfill({json:sheet});});
  await setup(page,score,'auto');const inline=page.locator('[data-note-id="retained"]').first();await expect(inline).toContainText('位置待確認');await inline.getByRole('button',{name:'編輯第1組歌詞與簡譜',exact:true}).click();await expect(page.getByLabel('筆記開始秒數')).toHaveValue('2');await revealNotes(page,'微調位置／文字行');await page.getByRole('button',{name:'確認歌詞與簡譜位置',exact:true}).click();await expect.poll(()=>sheet.document.lines[0].anchor.grid_id).not.toBe('old-grid');expect(sheet.document.lines[0].anchor.time).toBe(2);await expect(inline).not.toContainText('位置待確認');
  sheet={...sheet,version:sheet.version+1,document:{...sheet.document,lines:[{...sheet.document.lines[0],anchor:{...sheet.document.lines[0].anchor,time:2.1,grid_id:'old-grid'}}]}};
  await page.reload();await page.locator('[data-note-id="retained"]').first().getByRole('button',{name:'編輯第1組歌詞與簡譜',exact:true}).click();await revealNotes(page,'微調位置／文字行');await page.getByRole('button',{name:'確認歌詞與簡譜位置',exact:true}).click();await expect.poll(()=>sheet.document.lines[0].anchor.kind).toBe('seconds');expect(sheet.document.lines[0].anchor.time).toBe(2.1);expect(sheet.document.lines[0].anchor.grid_id).toBeNull();
});

test('legacy worksheet draft with same version cannot erase server anchors across refreshes',async({page})=>{
  const anchor={time:2,end:4,source_start_seconds:0,duration_seconds:8,kind:'metered',grid_id:fullNotePositions(score as any,readingBars(score as any))[0].grid_id};
  let sheet={...emptySheet(),version:5,document:{source:'saved',lines:[{id:'same-row',lyric:'server words',notation:'1 2',start:null,end:null,anchor}]}},puts=0;
  await page.addInitScript(()=>{if(!sessionStorage.getItem('legacy-draft-test-once')){sessionStorage.setItem('legacy-draft-test-once','yes');sessionStorage.setItem('guitarscribe.lyricWorksheetDraft.product-job',JSON.stringify({baseVersion:5,text:JSON.stringify({source:'saved',lines:[{id:'same-row',lyric:'舊頁面離線修改',notation:'5  0 -',start:null,end:null}]})}));}});
  await page.route('**/lyric-worksheet',r=>{if(r.request().method()==='GET')return r.fulfill({json:sheet});puts++;const body=r.request().postDataJSON();sheet={...sheet,document:body.document,version:sheet.version+1};return r.fulfill({json:sheet});});
  await setup(page,score,'auto');
  for(let i=0;i<3;i++){
    if(i)await page.reload();await openWorksheet(page);await expect(page.getByLabel('歌詞工作頁保存狀態')).toContainText('舊版草稿未包含定位資訊');
    await revealNotes(page,'選擇其他句／完整安排');await page.getByLabel('歌曲筆記安排').getByRole('button').first().click();await expect(page.getByLabel('歌詞第1行',{exact:true})).toHaveValue('舊頁面離線修改');
    expect(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('guitarscribe.lyricWorksheetDraft.product-job')!).anchor_schema)).toBeUndefined();expect(puts).toBe(0);expect(sheet.document.lines[0].anchor).toEqual(anchor);
  }
  await page.getByLabel('簡譜第1行',{exact:true}).fill('仍保留離線編輯');expect(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('guitarscribe.lyricWorksheetDraft.product-job')!).anchor_schema)).toBeUndefined();
  page.once('dialog',d=>d.accept());await revealNotes(page,'來源／備份／舊筆記');await page.getByRole('button',{name:'載入最新歌詞工作頁',exact:true}).click();await expect(page.getByLabel('歌詞第1行',{exact:true})).toHaveValue('server words');await expect(page.locator('[data-note-id="same-row"]')).toHaveCount(1);expect(puts).toBe(0);
});


// A24: paste once, type notation immediately, listen and mark each phrase.
async function quickLyrics(page:any,text:string){await page.getByLabel('貼上歌詞初稿').fill(text);await page.getByRole('button',{name:'加入歌詞',exact:true}).click();}
async function markerFixture(page:any,working:any,initial?:any){
  let sheet=initial??emptySheet(),compiles=0;const source=sourceWav(working.song.duration_seconds);
  await page.route('**/lyric-worksheet',r=>{if(r.request().method()==='GET')return r.fulfill({json:sheet});const body=r.request().postDataJSON();expect(body.anchor_schema).toBe(1);sheet={...sheet,document:body.document,version:sheet.version+1};return r.fulfill({json:sheet});});
  await page.route('**/scores/playback/manifest',r=>{compiles++;return r.fulfill({json:{revision:'lyric-clock',duration_seconds:working.song.duration_seconds,bpm:120,time_signature:'4/4',events:[{id:'g',track:'guitar',start:0,end:working.song.duration_seconds,sustain_end:working.song.duration_seconds,pitches:[48],pitch_offsets:[0],pitch_velocities:[98],velocity:98,source_id:'c'}]}});});
  await setup(page,working,'auto');await page.route('**/api/v1/jobs/product-job/audio',r=>r.fulfill({body:source,contentType:'audio/wav'}));await openWorksheet(page);
  return {sheet:()=>sheet,compiles:()=>compiles};
}

test('lyric marking uses source clock and point anchors, undo preserves edited text and rejects changed anchors',()=>{
  const document={source:'貼詞',lines:[newLine('第一句'),newLine('第二句')]},frame={duration_seconds:8,source_start_seconds:10};
  const context={currentTime:12},clock=createReviewTransportClock(context,{contextStart:10,scoreStart:1,end:7,loop:null},1);
  const first=markLyric(document,document.lines[0].id,clock.now(),frame);expect(first.document.lines[0].anchor?.time).toBe(3);expect(first.document.lines[0].anchor?.end).toBeNull();
  expect(()=>markLyric(first.document,document.lines[0].id,4,frame)).toThrow('已有位置');
  context.currentTime=13;const second=markLyric(first.document,document.lines[1].id,clock.now(),frame);expect(second.document.lines[0].anchor?.end).toBeNull();
  second.document.lines[1].notation=' 5  0 - ';second.document.lines[1].lyric='校對第二句';const undone=undoLyricMark(second.document,second.undo);expect(undone.lines[1].anchor).toBeNull();expect(undone.lines[1].notation).toBe(' 5  0 - ');expect(undone.lines[1].lyric).toBe('校對第二句');
  second.document.lines[1].anchor={...second.undo.after,time:5};expect(()=>undoLyricMark(second.document,second.undo)).toThrow('已被修改');
  expect(()=>markLyric(document,document.lines[0].id,8,frame)).toThrow('已結束');
  const loop=createReviewTransportClock(context,{contextStart:10,scoreStart:4,end:6,loop:[2,6]},2);expect(loop.now()).toBe(2);context.currentTime=13.25;expect(loop.now()).toBe(2.5);
});

for(const kind of ['metered','local','seconds'])test(`listen and mark short workflow preserves notes through chord edit and Undo (${kind})`,async({page})=>{
  await page.setViewportSize({width:320,height:844});
  if(kind==='seconds')await page.addInitScript(()=>{const calls:any[]=[];(window as any).__scrollCalls=calls;for(const name of ['scrollBy','scrollTo'] as const){const original=window[name].bind(window);(window as any)[name]=(...args:any[])=>{calls.push({name,args,stack:new Error().stack,y:scrollY});return (original as any)(...args);};}const original=Element.prototype.scrollIntoView;Element.prototype.scrollIntoView=function(...args:any[]){calls.push({name:'scrollIntoView',stack:new Error().stack,y:scrollY});return original.apply(this,args as any);};});
  const working=kind==='metered'?score:kind==='local'?partialScore:timelineScore;
  if(kind==='local')await page.route('**/timing-preview',r=>r.fulfill({json:partialPreview}));else await page.route('**/timing-preview',r=>r.fulfill({status:404}));
  const fixture=await markerFixture(page,working);await quickLyrics(page,'第一句歌詞\n第二句歌詞');await page.getByLabel('簡譜第1行',{exact:true}).fill("5  6 1' -");await expect.poll(()=>fixture.sheet().document.lines[0]?.notation).toBe("5  6 1' -");expect(fixture.sheet().document.lines[0].anchor).toBeNull();
  const lyricBox=await page.locator('.marking-current').boundingBox(),notationBox=await page.getByLabel('簡譜第1行',{exact:true}).boundingBox(),markBox=await page.getByRole('button',{name:'這句從這裡開始',exact:true}).boundingBox();expect(notationBox!.y).toBeGreaterThanOrEqual(lyricBox!.y+lyricBox!.height);expect(markBox!.y-notationBox!.y-notationBox!.height).toBeLessThan(30);await page.screenshot({path:`../output/evaluation/listen-mark-2026-11-07/${kind}-quick-fill-320.png`,fullPage:true});
  await expect(page.getByRole('button',{name:'這句從這裡開始',exact:true})).toBeDisabled();await page.getByRole('button',{name:'播放原曲',exact:true}).click();await expect(page.getByRole('button',{name:'暫停原曲',exact:true})).toBeVisible();await expect(page.getByLabel('播放聲音',{exact:true})).toHaveValue('source');
  if(kind==='local')await page.waitForTimeout(2150);else await page.waitForTimeout(250);
  const mark=page.getByRole('button',{name:'這句從這裡開始',exact:true});await mark.scrollIntoViewIfNeeded();const scroll=await page.evaluate(()=>scrollY),compiles=fixture.compiles(),beforeMark=await mark.boundingBox();await page.evaluate(()=>{if((window as any).__scrollCalls)(window as any).__scrollCalls.length=0;});await mark.click();await expect(page.getByLabel('簡譜第2行',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'暫停原曲',exact:true})).toBeVisible();
  await expect(mark).toBeEnabled();await mark.click();await expect.poll(()=>fixture.sheet().document.lines.filter((r:any)=>r.anchor).length).toBe(2);expect(fixture.compiles()).toBe(compiles);expect(Math.abs(await page.evaluate(()=>scrollY)-scroll),JSON.stringify({scroll,beforeMark,afterMark:await mark.boundingBox(),trace:await page.evaluate(()=>(window as any).__scrollCalls),transport:await page.locator('.timeline-transport').evaluate(el=>({position:getComputedStyle(el).position,rect:el.getBoundingClientRect().toJSON()}))})).toBeLessThan(3);
  const lines=fixture.sheet().document.lines;expect(lines[0].anchor.end).toBeNull();expect(lines[1].anchor.end).toBeNull();expect(lines[1].anchor.time).toBeGreaterThan(lines[0].anchor.time);
  await page.getByLabel('簡譜第2行',{exact:true}).fill('3 2  1');await page.getByRole('button',{name:'撤銷上次標記',exact:true}).click();await expect.poll(()=>fixture.sheet().document.lines[1].anchor).toBeNull();await expect(page.getByLabel('簡譜第2行',{exact:true})).toHaveValue('3 2  1');
  await expect(mark).toBeEnabled();await mark.click();await page.getByRole('button',{name:'暫停原曲',exact:true}).click();await expect(mark).toBeDisabled();await expect.poll(()=>fixture.sheet().document.lines[1].anchor).not.toBeNull();const before=JSON.stringify(fixture.sheet().document);
  await page.getByRole('button',{name:'查看譜上位置',exact:true}).click();const inline=page.locator(`[data-note-id="${lines[0].id}"]`).first();await expect(inline.locator('.located-lyric')).toHaveText('第一句歌詞');await expect(inline.locator('.located-notation')).toHaveText("5  6 1' -");
  await page.getByText('練習與編輯',{exact:true}).click();await page.getByRole('button',{name:kind==='metered'?'編輯和弦':'到時間表編輯',exact:true}).click();await page.getByRole('button',{name:/^編輯 .*的 C$/}).first().click();await page.getByLabel('和弦名稱',{exact:true}).fill('Em');await page.getByRole('button',{name:'套用和弦修改',exact:true}).click();await page.getByRole('button',{name:'復原',exact:true}).click();expect(JSON.stringify(fixture.sheet().document)).toBe(before);
  await page.reload();await expect(page.locator(`[data-note-id="${lines[0].id}"]`).first().locator('.located-notation')).toHaveText("5  6 1' -");expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:`../output/evaluation/listen-mark-2026-11-07/${kind}-320.png`,fullPage:true});
});

test('listen marking samples advancing audio clock even when rendered playhead is frozen',async({page})=>{
  await page.addInitScript(()=>{const raf=requestAnimationFrame.bind(window);window.requestAnimationFrame=callback=>callback.name==='updatePlayhead'?123456:raf(callback);});
  const fixture=await markerFixture(page,score);await quickLyrics(page,'一句\n二句');await page.getByRole('button',{name:'播放原曲',exact:true}).click();await expect(page.getByRole('button',{name:'暫停原曲',exact:true})).toBeVisible();await page.waitForTimeout(550);
  await expect(page.locator('.playback-status')).toContainText('0.0 /');await page.getByRole('button',{name:'這句從這裡開始',exact:true}).click();await expect.poll(()=>fixture.sheet().document.lines[0]?.anchor?.time).toBeGreaterThan(.3);expect(fixture.sheet().document.lines[0].anchor.end).toBeNull();await page.getByRole('button',{name:'暫停原曲',exact:true}).click();await expect(page.locator('.playback-status')).not.toContainText('0.0 /');
});

test('listen marking skips blank or title lines without deleting, and preserves existing positions',async({page})=>{
  const fixed={time:5,end:null,source_start_seconds:0,duration_seconds:8,kind:'seconds',grid_id:null};const initial={...emptySheet(),version:3,document:{source:'已有內容',lines:[newLine('歌曲標題'),newLine(''),newLine('第一句'),{...newLine('已經標記的句子'),anchor:fixed}]}};
  const fixture=await markerFixture(page,score,initial);await page.getByRole('button',{name:'略過這句',exact:true}).click();await expect(page.getByLabel('簡譜第3行',{exact:true})).toBeVisible();await page.getByRole('button',{name:'播放原曲',exact:true}).click();await expect(page.getByRole('button',{name:'這句從這裡開始',exact:true})).toBeEnabled();await page.getByRole('button',{name:'這句從這裡開始',exact:true}).dblclick();await expect.poll(()=>fixture.sheet().document.lines[2].anchor).not.toBeNull();expect(fixture.sheet().document.lines[0].anchor).toBeNull();expect(fixture.sheet().document.lines[1].anchor).toBeNull();expect(fixture.sheet().document.lines[3].anchor).toEqual(fixed);expect(fixture.sheet().document.lines).toHaveLength(4);
});

async function revealNotes(page:any,name:string){const summary=page.getByText(name,{exact:true});const details=summary.locator('..');if(await details.getAttribute('open')===null)await summary.click();}

test('listen marking cannot undo an anchor changed in fine tuning',async({page})=>{
  const fixture=await markerFixture(page,score);await quickLyrics(page,'校對一句');await page.getByLabel('簡譜第1行',{exact:true}).fill('原簡譜');await page.getByRole('button',{name:'播放原曲',exact:true}).click();await expect(page.getByRole('button',{name:'這句從這裡開始',exact:true})).toBeEnabled();await page.getByRole('button',{name:'這句從這裡開始',exact:true}).click();await page.getByRole('button',{name:'暫停原曲',exact:true}).click();
  await revealNotes(page,'微調位置／文字行');await page.getByLabel('筆記開始秒數').fill('3');await page.getByRole('button',{name:'確認歌詞與簡譜位置',exact:true}).click();await expect.poll(()=>fixture.sheet().document.lines[0]?.anchor?.time).toBe(3);await page.getByRole('button',{name:'撤銷上次標記',exact:true}).click();await expect(page.getByLabel('歌詞標記狀態')).toContainText('已被修改');expect(fixture.sheet().document.lines[0].anchor.time).toBe(3);expect(fixture.sheet().document.lines[0].notation).toBe('原簡譜');
});

test('listen marking unavailable source still allows immediate notation',async({page})=>{
  const working={...score,provenance:{...score.provenance,parameters:{candidate_source_job_id:'missing-original'}}};
  const fixture=await markerFixture(page,working,{...emptySheet(),job_id:'missing-original'});await quickLyrics(page,'可以先填');await page.getByLabel('簡譜第1行',{exact:true}).fill(' 5 6 0 - ');await expect.poll(()=>fixture.sheet().document.lines[0]?.notation).toBe(' 5 6 0 - ');await expect(page.getByRole('button',{name:'播放原曲',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'這句從這裡開始',exact:true})).toBeDisabled();await expect(page.getByText('原曲目前無法使用，仍可直接填簡譜；恢復原曲後再聽歌標記。',{exact:true})).toBeVisible();expect(fixture.compiles()).toBe(0);
});


test('listen marking button stays put between long and short phrases',async({page})=>{
  await page.setViewportSize({width:320,height:844});await markerFixture(page,score);await quickLyrics(page,'一個很長的句子需要在這個手機畫面分成兩行但不應該推動按鈕\n短句');await page.getByRole('button',{name:'播放原曲',exact:true}).click();const mark=page.getByRole('button',{name:'這句從這裡開始',exact:true});await expect(mark).toBeEnabled();await mark.scrollIntoViewIfNeeded();const before=await mark.boundingBox();await mark.click();await expect(page.locator('.marking-current strong')).toHaveText('短句');const after=await mark.boundingBox();expect(Math.abs(after!.y-before!.y)).toBeLessThan(1);await page.screenshot({path:'../output/evaluation/listen-mark-2026-11-07/short-phrase-320.png',fullPage:true});
});
