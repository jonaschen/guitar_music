import {test,expect} from '@playwright/test';
import {comparisonCore,structureSheet} from '../src/rootReuse';
const grid={bpm:60,beats:4,anchor:0};
test('comparison proposes complete equal bars and retains weak starts and different endings',()=>{
 const result=comparisonCore({start:1,end:19},{start:24,end:38},grid);
 expect(result).toEqual({source:{start:4,end:16},target:{start:24,end:36},bars:3,sourceExcluded:[{start:1,end:4},{start:16,end:19}],targetExcluded:[{start:36,end:38}]});
 expect(comparisonCore({start:1,end:3},{start:4,end:8},grid)).toBeNull();
});
test('structure sheet preserves actual order, unknown roots and changed references',()=>{
 const sections=[{id:'a',start:0,end:4,display_label:'副歌'},{id:'b',start:4,end:8,display_label:'主歌'},{id:'c',start:8,end:12,display_label:'副歌'}];
 const doc:any={source:{duration:12},segments:[{id:'r1',start:0,end:4,status:'confirmed',root:0},{id:'r2',start:4,end:8,status:'pending',root:null},{id:'r3',start:8,end:12,status:'confirmed',root:2}]};
 const op:any={id:'reuse',status:'applied',mapping_matches:false,target_matches:true,fully_equivalent:false,request:{source_range:{start:0,end:4},target_range:{start:8,end:12}},target_ids:['r3']};
 const result=structureSheet(sections as any,doc,[op]);
 expect(result.expanded_order.map((s:any)=>s.id)).toEqual(['a','b','c']);
 expect(result.expanded_order[1].roots[0].root).toBeNull();
 expect(result.expanded_order[2].references[0].state).toBe('待重新比較');
 expect(result.text).not.toContain('×2');expect(result.text).toContain('?');
 expect(result.metrics).toMatchObject({total:3,confirmed:2,pending:1,unsure:0,reused:0});
});

async function reuseFixture(page:any,version2=true,version=1){
 const source={job_id:'reuse-job',fingerprint:'a'.repeat(64),duration:16,source_start:0};
 const state:any={version,writes:0,plans:0,otherWrites:0,conflict:false,delay:false,operations:[],document:{schema_version:version2?2:1,...(version2?{grid}:{}),source,segments:[0,1,2,3].map((i)=>({id:'r'+i,start:i*4,end:(i+1)*4,root:i<2?[0,7][i]:null,original_root:null,status:i<2?'confirmed':i===3?'unsure':'pending'}))}};
 const structure={schema_version:1,candidate_sha256:null,source:{...source,audio_sha256:'b'.repeat(64)},sections:[0,1].map(i=>({id:'s'+i,start:i*8,end:(i+1)*8,label:'chorus',display_label:'副歌',name_review_status:'unreviewed',boundary_review_status:'unreviewed',model_sections:[],note:''}))};
 const snapshot=()=>({job_id:source.job_id,version:state.version,document:state.document,updated_at:null});
 await page.route('**/backend/**',async(r:any)=>{const path=new URL(r.request().url()).pathname,method=r.request().method();
  if(path.endsWith('/root-practice')){if(method==='PUT'){state.writes++;state.document=r.request().postDataJSON().document;state.version++;}return r.fulfill({json:snapshot()});}
  if(path.endsWith('/song-structure'))return r.fulfill({json:{job_id:source.job_id,version:1,document:structure,current_source:structure.source,source_matches:true}});
  if(path.endsWith('/reuse-ledger'))return r.fulfill({json:{job_id:source.job_id,version:state.version,source_matches:true,operations:state.operations}});
  if(path.endsWith('/reuse-plan')){state.plans++;const request=r.request().postDataJSON();return r.fulfill({json:{job_id:source.job_id,version:state.version,plan_id:'plan',request,grid,beat_count:8,rows:[{target_id:'r2',start:8,end:12,source_ids:['r0'],root:0,status:'fillable'},{target_id:'r3',start:12,end:16,source_ids:['r1'],root:7,status:'target_protected'}],counts:{fillable:1,target_protected:1},can_apply:request.alignment_confirmed}});}
  if(path.endsWith('/reuse-apply')){if(state.delay)await new Promise(r=>setTimeout(r,600));if(state.conflict)return r.fulfill({status:409,json:{detail:'版本已變動'}});state.writes++;const request=r.request().postDataJSON().request;state.document.segments[2]={...state.document.segments[2],root:0,status:'confirmed'};state.version++;state.operations=[{id:'op1',status:'applied',applied_version:state.version,request,source_ids:['r0'],target_ids:['r2'],mapping_matches:true,target_matches:true,can_undo:true,fully_equivalent:false,changes:[]}];return r.fulfill({json:{snapshot:snapshot(),operation:state.operations[0]}});}
  if(path.endsWith('/op1/undo')){state.writes++;state.document.segments[2]={...state.document.segments[2],root:null,status:'pending'};state.version++;state.operations[0].status='undone';state.operations[0].can_undo=false;return r.fulfill({json:{snapshot:snapshot(),operation:state.operations[0]}});}
  if(!['GET','HEAD'].includes(method))state.otherWrites++;
  if(path.endsWith('/capabilities'))return r.fulfill({json:{melody_available:false}});
  if(path.endsWith('/root-candidates'))return r.fulfill({json:{state:'idle',message:'fixture'}});
  return r.fulfill({status:404,json:{detail:'fixture'}});
 });
 await page.goto('/?practice=roots&job=reuse-job');await page.getByText('比較重複段與沿用',{exact:true}).click();await expect(page.getByLabel('比較來源大段')).toBeVisible();return state;
}
test('compare preview protects unsure roots, requires alignment, applies once and batch undoes after reload',async({page})=>{
 const state=await reuseFixture(page);await page.getByRole('button',{name:'預覽可沿用位置',exact:true}).click();
 await expect(page.getByLabel('沿用位置預覽')).toContainText('保留目前判斷');expect(state.writes).toBe(0);
 await expect(page.getByRole('button',{name:'沿用選取的 1 格',exact:true})).toBeDisabled();
 await page.getByLabel('我已回聽並確認兩個核心的拍位與根音可對應').check();
 await page.getByRole('button',{name:'預覽可沿用位置',exact:true}).click();await page.getByRole('button',{name:'沿用選取的 1 格',exact:true}).click();
 await expect.poll(()=>state.document.segments[2].root).toBe(0);expect(state.document.segments[3].status).toBe('unsure');expect(state.writes).toBe(1);
 await page.reload();await page.getByText('比較重複段與沿用',{exact:true}).click();await page.getByRole('button',{name:'撤銷這批沿用',exact:true}).click();
 await expect.poll(()=>state.document.segments[2].root).toBeNull();expect(state.document.segments[0].root).toBe(0);expect(state.otherWrites).toBe(0);
});
test('v1 can compare but cannot quietly regrid or copy same-name sections',async({page})=>{
 const state=await reuseFixture(page,false);await expect(page.getByText('先核對並套用小節分段，才能沿用。',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'預覽可沿用位置',exact:true})).toHaveCount(0);expect(state.writes).toBe(0);expect(state.plans).toBe(0);
});
test('stale apply retains worksheet and reports conflict rather than overwriting',async({page})=>{
 const state=await reuseFixture(page);state.conflict=true;await page.getByLabel('我已回聽並確認兩個核心的拍位與根音可對應').check();await page.getByRole('button',{name:'預覽可沿用位置',exact:true}).click();await page.getByRole('button',{name:'沿用選取的 1 格',exact:true}).click();
 await expect(page.getByLabel('根音保存狀態')).toContainText('版本');expect(state.document.segments[2].root).toBeNull();expect(state.writes).toBe(0);
});
test('changing compared bars invalidates preview and long requests cannot permit concurrent root edits',async({page})=>{
 const state=await reuseFixture(page);await page.getByLabel('我已回聽並確認兩個核心的拍位與根音可對應').check();await page.getByRole('button',{name:'預覽可沿用位置',exact:true}).click();
 await page.getByLabel('共同小節數').fill('1');await expect(page.getByLabel('沿用位置預覽')).toHaveCount(0);await expect(page.getByLabel('我已回聽並確認兩個核心的拍位與根音可對應')).not.toBeChecked();
 await page.getByLabel('我已回聽並確認兩個核心的拍位與根音可對應').check();await page.getByRole('button',{name:'預覽可沿用位置',exact:true}).click();state.delay=true;
 await page.getByRole('button',{name:'沿用選取的 1 格',exact:true}).click();await expect(page.getByLabel('根音保存狀態')).toContainText('整批');
 await expect(page.getByRole('button',{name:'還聽不出來',exact:true})).toBeDisabled();await expect.poll(()=>state.writes).toBe(1);
});
test('structure export includes chronological occurrences and unknown endings without writing',async({page})=>{
 const state=await reuseFixture(page);const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'下載結構譜 JSON',exact:true}).click()]);
 const stream=await download.createReadStream();let text='';for await(const chunk of stream!)text+=chunk.toString();const result=JSON.parse(text);expect(result.expanded_order).toHaveLength(2);expect(result.expanded_order[1].roots.map((r:any)=>r.root)).toEqual([null,null]);expect(result.metrics.confirmed).toBe(2);expect(state.writes).toBe(0);
});
test('only confirmed whole adjacent equivalents compress; different endings remain expanded',()=>{
 const sections=[{id:'a',start:0,end:8,display_label:'副歌'},{id:'b',start:8,end:16,display_label:'副歌'},{id:'c',start:16,end:24,display_label:'副歌'}];
 const doc:any={source:{duration:24},segments:Array.from({length:6},(_,i)=>({id:'r'+i,start:i*4,end:i*4+4,status:'confirmed',root:i%2?7:0}))};
 const operation:any={id:'reuse',status:'applied',mapping_matches:true,target_matches:true,fully_equivalent:true,request:{source_range:{start:0,end:8},target_range:{start:8,end:16}},target_ids:['r2','r3']};
 const tail:any={...operation,id:'tail',request:{source_range:{start:0,end:4},target_range:{start:16,end:20}},target_ids:['r4']};
 const result=structureSheet(sections as any,doc,[operation,tail]);
 expect(result.notation[0]).toMatchObject({occurrence_ids:['a','b'],repeat:2});expect(result.notation[1].repeat).toBe(1);
 expect(result.text).toContain('×2');expect(result.expanded_order[2].references[0].exceptions).toEqual([{start:20,end:24}]);expect(result.expanded_order).toHaveLength(3);
});
test('deferred practice is remembered locally and never counted as adopted roots',async({page})=>{
 const state=await reuseFixture(page);await page.getByRole('button',{name:'暫不練第 2 段',exact:true}).click();
 await expect(page.getByLabel('結構譜與工作量')).toContainText('暫不練 2');await expect(page.getByLabel('結構譜與工作量')).toContainText('已採用 2／4');
 await page.reload();await page.getByText('比較重複段與沿用',{exact:true}).click();await expect(page.getByRole('button',{name:'恢復練習第 2 段',exact:true})).toBeVisible();expect(state.writes).toBe(0);
});
test('expanded structure clips crossing roots for display while preserving original decision bounds',()=>{
 const sections=[{id:'a',start:0,end:5,display_label:'主歌'},{id:'b',start:5,end:12,display_label:'副歌'}];
 const doc:any={source:{duration:12},segments:[{id:'r0',start:0,end:4,status:'confirmed',root:0},{id:'r1',start:4,end:8,status:'confirmed',root:7},{id:'r2',start:8,end:12,status:'pending',root:null}]};
 const sheet=structureSheet(sections as any,doc,[]);
 expect(sheet.expanded_order.flatMap(s=>s.roots.map(r=>[r.start,r.end]))).toEqual([[0,4],[4,5],[5,8],[8,12]]);
 expect(sheet.expanded_order[1].roots[0]).toMatchObject({id:'r1',original_start:4,original_end:8});expect(doc.segments[1].start).toBe(4);expect(sheet.metrics.total).toBe(3);
});
test('dirty or newly saved roots cannot export a still-loading old reuse relationship as valid',async({page})=>{
 const state=await reuseFixture(page);await page.getByLabel('我已回聽並確認兩個核心的拍位與根音可對應').check();await page.getByRole('button',{name:'預覽可沿用位置',exact:true}).click();await page.getByRole('button',{name:'沿用選取的 1 格',exact:true}).click();await expect(page.getByLabel('結構譜與工作量')).toContainText('有效沿用 1');
 await page.route('**/root-practice/reuse-ledger',async r=>{await new Promise(resolve=>setTimeout(resolve,2500));await r.fulfill({json:{job_id:'reuse-job',version:state.version,source_matches:true,operations:state.operations.map((o:any)=>({...o,mapping_matches:false}))}});});
 await page.getByRole('button',{name:'還聽不出來',exact:true}).click();await expect(page.getByLabel('結構譜與工作量')).toContainText('有效沿用 0');await expect(page.getByLabel('根音保存狀態')).toHaveText('已保存');
 const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'下載結構譜 JSON',exact:true}).click()]);let text='';for await(const chunk of (await download.createReadStream())!)text+=chunk.toString();expect(JSON.parse(text).metrics.reused).toBe(0);
});
for(const width of [390,1440])test(`comparison remains readable at ${width}px with explicit stop control`,async({page})=>{
 await page.setViewportSize({width,height:900});await reuseFixture(page);await expect(page.getByRole('button',{name:'停止比較播放',exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.getByLabel('共同小節數').focus();await expect(page.getByLabel('共同小節數')).toBeFocused();
});

test('initial automatic grid explains why reuse waits for a saved source decision',async({page})=>{
 const state=await reuseFixture(page,true,0);await expect(page.getByText('先在來源大段採用根音並保存，再預覽沿用。',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'預覽可沿用位置',exact:true})).toBeDisabled();expect(state.writes).toBe(0);
});
