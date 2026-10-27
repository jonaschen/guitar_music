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

async function setup(page:any) {
  await page.addInitScript(()=>{localStorage.setItem('guitarscribe.editorView','melody');localStorage.setItem('guitarscribe.workspaceMode','full');});
  await page.route('**/api/v1/capabilities',r=>r.fulfill({json:{melody_available:true,youtube_enabled:true,vocal_separation_enabled:true}}));
  const archived={...score,melody:[{id:'n',start:0,end:1,midi:60,note:'C4',confidence:1,origin:'model',edited:false}]};
  await page.route('**/api/v1/jobs/product-job',r=>r.fulfill({json:{id:'product-job',status:'completed',progress:100,artifacts:[],score:archived}}));
  await page.route('**/api/v1/jobs/product-job/audio',r=>r.fulfill({status:404,body:''}));
  await page.route('**/revisions/*/history',r=>r.fulfill({json:[]}));
  await page.route('**/revisions',r=>r.fulfill({json:{revision_id:'auto-saved'}}));
  await page.route('**/rhythm-patterns?*',r=>r.fulfill({json:[]}));
  await page.goto('/?job=product-job&view=melody');
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
for(const width of [320,390,768,1440])test(`four-bar notation and progressive controls at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:844});await setup(page);
  await expect(page.getByLabel('歌曲調性')).toBeVisible();
  await expect(page.getByLabel('歌曲 Capo')).toBeVisible();
  await expect(page.getByRole('button',{name:'復原',exact:true})).toBeHidden();
  const bars=page.locator('.notation-measure');expect(await bars.count()).toBe(4);
  const bounds=await bars.evaluateAll(els=>els.map(el=>el.getBoundingClientRect().top));
  expect(new Set(bounds).size).toBe(1);
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
