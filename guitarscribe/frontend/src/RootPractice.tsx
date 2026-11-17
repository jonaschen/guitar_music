import {useCallback,useEffect,useRef,useState} from 'react';
import {RootPracticeGrid} from './RootPracticeGrid';
import {RootReusePanel} from './RootReusePanel';
import {RootStructureNav,type PracticeSection} from './RootStructureNav';
import {RootSpectrogram} from './RootSpectrogram';
import {regridRoots,subdivideRootBar,rootSegmentLabel} from './rootMetricalSegments';
import type {RootGrid} from './rootPracticeGrid';
import {useRootPractice} from './useRootPractice';
import {ROOT_NAMES,mergeRootSegment,parseRootDocument,rootStamp,rootText,splitRootSegment,type RootDocument} from './rootPracticeDocument';
import {RootPracticeAudio,type RootAudioMode} from './rootPracticeAudio';
import {ROOT_AUDITION_MIN,ROOT_AUDITION_MAX,ROOT_AUDITION_ORDER,rootAuditionMidi,rootAuditionName,auditionMidiName} from './rootPracticePitch';
import './rootPractice.css';

type Candidate={pitch_class:number;name:string;rank:number;score:number};
type EvidenceState={state:string;message:string};
type SegmentPlan={document:RootDocument;bars:number;exceptions:Array<{bar:number;start:number;end:number;parts:number}>;review:Array<{start:number;end:number;roots:number[]}>;preserved:number;evidence_available:boolean;note:string;base:string};
type PlaybackScope='segment'|'whole'|'range'|'locate';
export function RootPractice({job,title,api,onClose}:{job:string;title:string;api:string;onClose:()=>void}){
  const sheet=useRootPractice(api,job),doc=sheet.document;
  const [practiceSection,setPracticeSection]=useState<PracticeSection|null>(null);
  const [selected,setSelected]=useState(''),[trial,setTrial]=useState<number|null>(null);
  const selectedSeek=useRef<{id:string;time:number}|null>(null);
  const [position,setPosition]=useState(0),[audioState,setAudioState]=useState<'idle'|'preparing'|'playing'>('idle');
  const [playbackBounds,setPlaybackBounds]=useState<{start:number;end:number}|null>(null);
  const [mode,setMode]=useState<RootAudioMode>('source'),[loop,setLoop]=useState(true),[context,setContext]=useState(true);
  const [toolsOpen,setToolsOpen]=useState(()=>{try{return sessionStorage.getItem('guitarscribe.root-tools')==='open';}catch{return false;}});
  const toolsPanel=useRef<HTMLDetailsElement>(null);
  function showTools(open:boolean){setToolsOpen(open);try{sessionStorage.setItem('guitarscribe.root-tools',open?'open':'closed');}catch{/* Optional preference. */}}
  const [sourceVolume,setSourceVolume]=useState(.75),[rootVolume,setRootVolume]=useState(.5),[hideClues,setHideClues]=useState(false);
  const [notice,setNotice]=useState(''),[scope,setScope]=useState<PlaybackScope>('segment');
  const [rangeStart,setRangeStart]=useState('0'),[rangeEnd,setRangeEnd]=useState(''),[rangeLoop,setRangeLoop]=useState(true);
  const [rangeNotice,setRangeNotice]=useState('');
  const comparisonAudio=useRef<{start:number;end:number;sha:string}|null>(null);
  const [gridSettings,setGridSettings]=useState<RootGrid|null>(null),[plan,setPlan]=useState<SegmentPlan|null>(null),[planBusy,setPlanBusy]=useState(false),[planNotice,setPlanNotice]=useState('');
  const [metronomeActive,setMetronomeActive]=useState(false);
  const [archives,setArchives]=useState<Array<{version:number;document:RootDocument}>>([]);
  const [historyNotice,setHistoryNotice]=useState('');
  const planRequest=useRef<AbortController|null>(null),planPanel=useRef<HTMLDivElement|null>(null);
  useEffect(()=>{if(plan)planPanel.current?.scrollIntoView({block:'nearest'});},[plan]);
  const gridChanged=doc?.schema_version!==2||JSON.stringify(doc.grid)!==JSON.stringify(gridSettings);
  const updateGridSettings=useCallback((grid:RootGrid|null)=>setGridSettings(old=>JSON.stringify(old)===JSON.stringify(grid)?old:grid),[]);
  const [evidence,setEvidence]=useState<EvidenceState>({state:'loading',message:'正在查看參考音…'}),[candidates,setCandidates]=useState<Candidate[]>([]),[clueMessage,setClueMessage]=useState('');
  const alive=useRef(true),request=useRef<AbortController|null>(null),rankRequest=useRef<AbortController|null>(null);
  const progression=useRef<HTMLElement|null>(null);
  const [player]=useState(()=>new RootPracticeAudio((t,s,error)=>{if(alive.current){setPosition(t);setAudioState(s);if(error)setNotice(error);}}));
  const setMetronome=useCallback((grid:RootGrid|null)=>{player.metronome(grid);setMetronomeActive(!!grid);},[player]);
  const index=Math.max(0,doc?.segments.findIndex(s=>s.id===selected)??0),segment=doc?.segments[index];
  const endpoint=`${api}/api/v1/jobs/${encodeURIComponent(job)}`;
  const range={start:rangeStart.trim()?Number(rangeStart):NaN,end:rangeEnd.trim()?Number(rangeEnd):NaN};
  const rangeValid=!!doc&&Number.isFinite(range.start+range.end)&&range.start>=0&&range.end<=doc.source.duration&&range.end-range.start>=.08;
  useEffect(()=>{
    if(!doc)return;
    let savedSegment:string|null=null;try{savedSegment=sessionStorage.getItem(`guitarscribe.root-position.${doc.source.fingerprint}`);}catch{/* Optional preference. */}
    const initial=doc.segments.find(s=>s.id===savedSegment)??doc.segments.find(s=>s.original_root!==null&&s.end-s.start>=.5&&s.status!=='confirmed')??doc.segments[0];
    let start=initial.start,end=initial.end,repeat=true;
    try{const saved=JSON.parse(sessionStorage.getItem(`guitarscribe.root-range.${doc.source.fingerprint}`)??'null');
      if(saved&&Number.isFinite(saved.start+saved.end)&&saved.start>=0&&saved.end<=doc.source.duration&&saved.end-saved.start>=.08){start=saved.start;end=saved.end;repeat=saved.loop!==false;}
    }catch{/* Range preferences never block access to the score. */}
    setRangeStart(String(start));setRangeEnd(String(end));setRangeLoop(repeat);
  },[doc?.source.fingerprint]);
  useEffect(()=>{
    if(doc&&rangeValid)try{sessionStorage.setItem(`guitarscribe.root-range.${doc.source.fingerprint}`,JSON.stringify({...range,loop:rangeLoop}));}catch{/* Optional local preference. */}
  },[doc?.source.fingerprint,rangeStart,rangeEnd,rangeLoop]);
  useEffect(()=>{
    if(!doc)return;
    const key=`guitarscribe.root-position.${doc.source.fingerprint}`;
    if(!selected||!doc.segments.some(s=>s.id===selected)){
      let saved:string|null=null;try{saved=sessionStorage.getItem(key);}catch{/* Keep the musical default. */}
      const next=doc.segments.find(s=>s.id===saved)??(selected?doc.segments.find(s=>position>=s.start&&position<s.end):undefined)??doc.segments.find(s=>s.original_root!==null&&s.end-s.start>=.5&&s.status!=='confirmed')??doc.segments[0];
      setSelected(next.id);
    }else try{sessionStorage.setItem(key,selected);}catch{/* Position is not a musical edit. */}
  },[selected,doc?.source.fingerprint,doc?.segments.length]);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;request.current?.abort();rankRequest.current?.abort();player.dispose();};},[player]);
  useEffect(()=>{player.volume(sourceVolume,rootVolume);},[sourceVolume,rootVolume,player]);
  useEffect(()=>{
    if(!segment)return;
    const seek=selectedSeek.current;selectedSeek.current=null;
    player.stop();setTrial(segment.root===null?null:rootAuditionMidi(segment.root));setPosition(seek?.id===segment.id?seek.time:segment.start);setScope('segment');
  },[segment?.id,segment?.start,segment?.end,doc?.source.fingerprint]);
  useEffect(()=>{
    const nav=progression.current;if(!nav)return;
    const center=()=>{const button=nav.querySelector<HTMLElement>('[aria-current=step]');if(button){const n=nav.getBoundingClientRect(),b=button.getBoundingClientRect();nav.scrollLeft+=b.left-n.left-(n.width-b.width)/2;}};
    center();const observer=new ResizeObserver(center);observer.observe(nav);return()=>observer.disconnect();
  },[segment?.id,doc?.segments.length]);
  async function refreshEvidence(method='GET'){
    request.current?.abort();const controller=new AbortController();request.current=controller;
    try{
      const response=await fetch(`${endpoint}/root-candidates`,{method,signal:controller.signal});
      if(!response.ok)throw Error('參考音暫時無法取得，可先自行聽辨。');
      const state=await response.json() as EvidenceState;
      if(!controller.signal.aborted)setEvidence(state);
    }catch(error){if(!controller.signal.aborted)setEvidence({state:'failed',message:error instanceof Error?error.message:'參考音暫時無法取得。'});}
  }
  useEffect(()=>{if(doc)void refreshEvidence();},[doc?.source.fingerprint]);
  useEffect(()=>{if(!['running','cancelling'].includes(evidence.state))return;const timer=setTimeout(()=>void refreshEvidence(),1200);return()=>clearTimeout(timer);},[evidence]);
  useEffect(()=>{
    rankRequest.current?.abort();setCandidates([]);
    if(!doc||!segment||evidence.state!=='ready'){setClueMessage('尚無這段的參考音，可以選「其他音」自行比較。');return;}
    const controller=new AbortController();rankRequest.current=controller;setClueMessage('正在整理這段線索…');
    void (async()=>{try{
      const response=await fetch(`${endpoint}/root-candidates/rank`,{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,
        body:JSON.stringify({fingerprint:doc.source.fingerprint,start:segment.start,end:segment.end})});
      if(!response.ok)throw Error('這段線索暫時無法取得，可以選其他音。');
      const result=await response.json();
      if(controller.signal.aborted||result.fingerprint!==doc.source.fingerprint||result.start!==segment.start||result.end!==segment.end)return;
      setCandidates(result.candidates??[]);setClueMessage(result.status==='available'?'三個參考音都可能不合；可選其他音，或先保留待聽。':result.status==='ambiguous'?'這段線索太接近，無法區分前三個音。請自行選音或先跳過。':'這段線索不足，請自行選音或先跳過。');
    }catch(error){if(!controller.signal.aborted)setClueMessage(error instanceof Error?error.message:'線索取得失敗。');}})();
    return()=>controller.abort();
  },[doc?.source.fingerprint,segment?.id,segment?.start,segment?.end,evidence.state]);

  useEffect(()=>{planRequest.current?.abort();setPlan(null);setPlanBusy(false);setPlanNotice('');},[doc,gridSettings]);
  useEffect(()=>()=>planRequest.current?.abort(),[]);
  function localPlan(next:RootDocument,note:string):SegmentPlan{
    return {document:next,bars:0,exceptions:[],review:next.segments.filter(s=>s.status==='unsure').map(s=>({start:s.start,end:s.end,roots:[...new Set((doc?.segments??[]).filter(old=>old.status==='confirmed'&&old.start<s.end-1e-8&&old.end>s.start+1e-8).map(old=>old.root!))]})),preserved:next.segments.filter(s=>s.status==='confirmed').length,evidence_available:false,note,base:JSON.stringify(doc)};
  }
  async function previewSegments(){
    if(!doc||!gridSettings)return;
    planRequest.current?.abort();const controller=new AbortController();planRequest.current=controller;setPlanBusy(true);setPlanNotice('');setPlan(null);
    try{
      const response=await fetch(`${endpoint}/root-practice/segment-plan`,{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({document:doc,grid:gridSettings})});
      if(!response.ok)throw Error(response.status===409?'來源已變動，請先下載備份再重新載入。':'分段預覽暫時無法取得，可使用「只按整小節重排」。');
      const result=await response.json();const next=parseRootDocument(JSON.stringify(result.document),doc.source);
      if(!controller.signal.aborted)setPlan({...result,document:next,base:JSON.stringify(doc)});
    }catch(error){if(!controller.signal.aborted)setPlanNotice(error instanceof Error?error.message:'預覽失敗。');}
    finally{if(!controller.signal.aborted)setPlanBusy(false);}
  }
  function previewWholeBars(){if(!doc||!gridSettings)return;planRequest.current?.abort();setPlanBusy(false);try{setPlan(localPlan(regridRoots(doc,gridSettings),'只按整小節重排，未加入自動細分。'));setPlanNotice('');}catch(error){setPlanNotice(String(error));}}
  function previewSubdivision(divisor:1|2|4){
    if(!doc||!segment)return;try{setPlan(localPlan(subdivideRootBar(doc,(segment.start+segment.end)/2,divisor),'手動調整目前小節；所有邊界對齊拍格。'));setPlanNotice('');}catch(error){setPlanNotice(String(error));}
  }
  function applyPlan(){
    if(!plan||!doc||plan.base!==JSON.stringify(doc))return;
    const time=audioState==='playing'?player.read():position;player.stop();
    if(sheet.update(plan.document)){setSelected((plan.document.segments.find(s=>time>=s.start&&time<s.end)??plan.document.segments[0]).id);setTrial(null);setPlan(null);setNotice('已套用小節分段；保存成功後，原版本會封存在「歷次保存」。');}
  }
  async function loadArchives(){
    setHistoryNotice('正在載入歷次保存…');
    try{const response=await fetch(`${endpoint}/root-practice/history`);if(!response.ok)throw Error();const data=await response.json();setArchives(data.map((a:{version:number;document:RootDocument})=>({...a,document:parseRootDocument(JSON.stringify(a.document),doc!.source)})));setHistoryNotice(data.length?'':'目前沒有較早版本。');}catch{setHistoryNotice('歷次保存暫時無法載入。');}
  }
  function restoreArchive(archive:RootDocument){if(!doc)return;const next=archive.schema_version===1?regridRoots(archive,doc.grid??gridSettings??{bpm:115,beats:4,anchor:0}):archive;showTools(true);setPlan(localPlan(next,'恢復歷次保存；舊版非拍格稿會先轉為目前小節長度。'));}
  function chooseSegment(id:string,time?:number,alignRange=true){
    const next=doc?.segments.find(s=>s.id===id);if(!next)return;
    const at=time??next.start;
    if(practiceSection&&(next.end<=practiceSection.start||next.start>=practiceSection.end))setPracticeSection(null);
    selectedSeek.current=id!==segment?.id?{id,time:at}:null;
    player.stop();setSelected(id);setTrial(next.root===null?null:rootAuditionMidi(next.root));setPosition(at);
    if(alignRange){setRangeStart(String(next.start));setRangeEnd(String(next.end));}
    setMode('source');setNotice('');setScope('segment');
  }
  function seekVisual(time:number){
    const next=doc?.segments.find(s=>time>=s.start&&time<s.end);if(!next)return;
    if(next.id!==segment?.id)chooseSegment(next.id,time,false);
    else{player.stop();setPosition(time);setScope('locate');}
  }
  function play(midi=trial,audioMode=mode,nextScope:PlaybackScope='segment',from?:number){
    if(!doc||!segment)return;
    if(nextScope==='range'&&!rangeValid){setNotice('請選擇有效的連聽起點與終點。');return;}
    setNotice('');setScope(nextScope);
    const start=nextScope==='range'?range.start:nextScope!=='segment'?0:Math.max(0,segment.start-(context ? .75 : 0));
    const end=nextScope==='range'?range.end:nextScope!=='segment'?doc.source.duration:Math.min(doc.source.duration,segment.end+(context ? .75 : 0));
    setPlaybackBounds({start,end});
    if(nextScope!=='segment'){audioMode=nextScope==='locate'||nextScope==='range'&&audioMode==='source'?'source':'mix';setMode(audioMode);}
    const notes=audioMode==='source'?[]:nextScope!=='segment'?doc.segments.filter(s=>s.status==='confirmed'&&s.root!==null&&s.start<end&&s.end>start).map(s=>({start:Math.max(start,s.start),end:Math.min(end,s.end),root:s.root!})):midi===null?[]:[{start,end,root:midi%12,midi}];
    void player.play({url:`${endpoint}/root-practice/audio?fingerprint=${doc.source.fingerprint}`,start,end,from,loop:nextScope==='range'?rangeLoop:nextScope!=='segment'?false:loop,mode:audioMode,notes});
  }
  function editRange(start:string,end:string){comparisonAudio.current=null;player.stop();setRangeStart(start);setRangeEnd(end);setScope('range');setRangeNotice('');setPosition(Math.max(0,Math.min(doc?.source.duration??0,Number.isFinite(Number(start))?Number(start):0)));}
  function dragBoundary(side:'start'|'end',time:number){
    if(!doc)return;
    const start=Number.isFinite(range.start)?range.start:0,end=Number.isFinite(range.end)?range.end:doc.source.duration;
    if(side==='start')editRange(String(Math.max(0,Math.min(time,doc.source.duration-.08,end-.08))),String(end));
    else editRange(String(start),String(Math.min(doc.source.duration,Math.max(time,.08,start+.08))));
  }
  function markBoundary(side:'start'|'end'){
    if(!doc)return;
    const time=Math.max(0,Math.min(doc.source.duration,Math.round((audioState==='playing'?player.read():position)*100)/100));
    const start=side==='start'?time:range.start;
    const end=side==='end'?time:Number.isFinite(range.end)&&range.end>=start+.08?range.end:doc.source.duration;
    if(!Number.isFinite(start+end)||start<0||end>doc.source.duration||end-start<.08){setRangeNotice('起點須早於終點；可先拖動另一端，再設定目前位置。');return;}
    if(scope==='locate'&&audioState==='playing'){setRangeStart(String(start));setRangeEnd(String(end));}
    else editRange(String(start),String(end));
    setRangeNotice(`已設${side==='start'?'起點':'終點'} ${rootStamp(time)}`);
  }
  function locateRange(){
    if(scope==='locate'&&audioState!=='idle'){player.stop();return;}
    play(null,'source','locate',doc&&position>=0&&position<doc.source.duration?position:0);
  }
  function rangeBoundary(side:'start'|'end',i:number){
    const s=doc?.segments[i];if(!s)return;
    if(side==='start')editRange(String(s.start),String(Number.isFinite(range.end)&&range.end>s.start?range.end:s.end));
    else editRange(String(Number.isFinite(range.start)&&range.start<s.end?range.start:s.start),String(s.end));
  }
  function toggleRange(){
    if(scope==='range'&&audioState!=='idle'){player.stop();return;}
    play(null,scope==='range'&&mode==='source'?'source':'mix','range',scope==='range'&&position>=range.start&&position<range.end?position:undefined);
  }
  function playVisualRange(start:number,end:number,from?:number,repeat=true,audioSha?:string){
    if(!doc||!Number.isFinite(start+end)||start<0||end>doc.source.duration||end-start<.08)return;
    if(audioSha)comparisonAudio.current={start,end,sha:audioSha};
    else if(comparisonAudio.current&&(comparisonAudio.current.start!==start||comparisonAudio.current.end!==end))comparisonAudio.current=null;
    const boundSha=audioSha??comparisonAudio.current?.sha;
    setRangeStart(String(start));setRangeEnd(String(end));setRangeLoop(repeat);setScope('range');setMode('source');setNotice('');setPlaybackBounds({start,end});
    void player.play({url:boundSha?`${endpoint}/song-structure/audio?fingerprint=${doc.source.fingerprint}&audio_sha256=${boundSha}`:`${endpoint}/root-practice/audio?fingerprint=${doc.source.fingerprint}`,start,end,from,loop:repeat,mode:'source',notes:[]});
  }
  function primaryPlayback(){
    if(audioState!=='idle'){player.stop();return;}
    if(rangeValid)playVisualRange(range.start,range.end,scope==='range'&&position>=range.start&&position<range.end?position:undefined,rangeLoop);
  }
  function audition(midi:number){setTrial(midi);const next=mode==='source'?'mix':mode;setMode(next);play(midi,next);}
  function stepPitch(direction:-1|1){
    if(trial===null)return;
    const midi=trial+direction;
    if(midi>=ROOT_AUDITION_MIN&&midi<=ROOT_AUDITION_MAX)audition(midi);
  }
  function togglePlayback(){
    if(audioState!=='idle'){player.stop();return;}
    if(!doc||!segment)return;
    const inRange=scope==='range'?position>=range.start&&position<range.end:scope!=='segment'?position>=0&&position<doc.source.duration:position>=segment.start&&position<segment.end;
    play(trial,mode,scope,inRange?position:undefined);
  }
  function decision(root:number|null,status:'confirmed'|'unsure'){
    if(!doc||!segment)return;
    if(scope!=='segment')player.stop(); // Resume with current decisions, never a stale scheduled root.
    if(sheet.update({...doc,segments:doc.segments.map(s=>s.id===segment.id?{...s,root,status}:s)})){
      setNotice(status==='confirmed'?`已採用 ${ROOT_NAMES[root!]}；這是你的聽辨判斷。`:'已保留待聽，可隨時回來。');
      if(status==='unsure'){player.stop();setTrial(null);}
    }
  }
  function structure(action:'split'|'merge'){
    if(!doc||!segment)return;const time=audioState==='idle'?position:player.read();player.stop();
    try{const next=action==='split'?splitRootSegment(doc,segment.id,time):mergeRootSegment(doc,segment.id);if(sheet.update(next)){setTrial(null);setNotice('區段已調整，相關根音改為待聽；可復原。');}}
    catch(error){setNotice(error instanceof Error?error.message:'區段調整失敗。');}
  }
  function download(text:string,name:string,type='application/json'){
    const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function importBackup(file:File){
    if(!doc)return;
    try{if(file.size>3_000_000)throw Error('備份檔太大，請選根音練習 JSON。');const imported=parseRootDocument(await file.text(),doc.source);const next=doc.schema_version===2&&imported.schema_version===1?regridRoots(imported,doc.grid!):imported;player.stop();if(sheet.update(next)){setSelected(next.segments[0].id);setTrial(null);setNotice('已還原備份，可以復原。');}}
    catch(error){setNotice(error instanceof Error?error.message:'備份無法讀取。');}
  }
  function history(back:boolean){player.stop();setTrial(null);if(back)sheet.undo();else sheet.redo();setNotice('已還原練習內容，請重新選音試聽。');}
  function selectPracticeSection(section:PracticeSection|null){
    setPracticeSection(section);if(!doc)return;player.stop();
    if(section){const next=doc.segments.find(s=>s.start<section.end&&s.end>section.start);if(next){chooseSegment(next.id,Math.max(section.start,next.start),false);setPracticeSection(section);}editRange(String(section.start),String(section.end));}
  }
  const visibleSegments=(doc?.segments??[]).map((s,i)=>({s,i})).filter(({s})=>!practiceSection||s.start<practiceSection.end&&s.end>practiceSection.start);
  const visibleIndex=visibleSegments.findIndex(({s})=>s.id===segment?.id);
  useEffect(()=>{if(practiceSection&&segment&&(segment.end<=practiceSection.start||segment.start>=practiceSection.end))setPracticeSection(null);},[practiceSection,segment?.id,segment?.start,segment?.end]);
  const confirmed=doc?.segments.filter(s=>s.status==='confirmed').length??0;
  const playingIndex=doc?.segments.findIndex(s=>position>=s.start&&position<s.end)??-1;
  const playingSegment=playingIndex>=0?doc?.segments[playingIndex]:undefined;
  const editable=!!doc&&!sheet.blocked&&!sheet.transaction;
  const candidateBusy=['running','cancelling'].includes(evidence.state);
  return <main className="root-practice" aria-label="根音抓歌練習">
    <header className="root-header"><div><h1>{title}</h1><p>根音抓歌練習 · 一段一段，聽出自己的版本</p></div><button type="button" onClick={()=>{player.stop();onClose();}}>返回和弦頁</button></header>
    <p className="root-intro">聽原曲、比較單音，決定這段要用哪個根音。參考音仍屬實驗線索，沒有標準答案評分。</p>
    <div className="root-save"><span role="status" aria-label="根音保存狀態">{sheet.message}</span><span>{confirmed} 段已採用 · {(doc?.segments.length??0)-confirmed} 段待聽</span></div>
    {sheet.blocked?<div className="root-problem" role="alert"><p>請先保留本頁內容，再處理保存問題。</p><button onClick={()=>download(sheet.rawDraft(),`root-draft-${job}.json`)}>下載原始草稿</button><button onClick={sheet.retry}>重試保存／載入</button><button disabled={sheet.busy} onClick={()=>{if(confirm('確定已下載需要保留的草稿？載入最新版本會替換本頁未保存內容。'))sheet.loadLatest();}}>載入最新版本</button></div>:null}
    {doc&&segment?<>
      <RootStructureNav api={api} job={job} document={doc} active={practiceSection} onSelect={selectPracticeSection}/>
      <RootReusePanel api={api} job={job} document={doc} version={sheet.version} ready={!sheet.blocked&&!sheet.busy&&sheet.synced&&!gridChanged} serverAction={sheet.serverAction} onListen={(range,audioSha)=>{player.metronome(null);setMetronomeActive(false);playVisualRange(range.start,range.end,undefined,false,audioSha);}} onStop={()=>player.stop()} onGrid={()=>{showTools(true);toolsPanel.current?.scrollIntoView({block:'nearest'});}}/>
      <nav className="root-progression" ref={progression} aria-label="根音行進">{visibleSegments.map(({s,i})=><button type="button" key={s.id} aria-current={segment.id===s.id?'step':undefined} data-playing={audioState==='playing'&&position>=s.start&&position<s.end} aria-label={`第 ${i+1} 段 ${s.root===null?'待聽':ROOT_NAMES[s.root]} ${rootStamp(s.start)}`} onClick={()=>chooseSegment(s.id)}><small>{doc.grid?rootSegmentLabel(doc,s).split(' · ').slice(0,2).join(' · '):i+1}</small>{doc.grid?<small>{rootSegmentLabel(doc,s).split(' · ')[2]}</small>:null}<strong>{s.root===null?'?':ROOT_NAMES[s.root]}</strong><span>{s.status==='confirmed'?'已採用':s.status==='unsure'?'再聽':'待聽'}</span></button>)}</nav>
      <section className="root-workflow-transport" aria-label="主要播放控制">
        <div><strong>先聽原曲，再比較</strong><p aria-label="主要播放範圍">原曲 A–B：{rangeValid?`${rootStamp(range.start)}–${rootStamp(range.end)}`:'請設定有效範圍'}</p>{audioState!=='idle'&&playbackBounds?<p aria-label="正在播放範圍">{audioState==='preparing'?'準備播放':'正在播放'}：{rootStamp(playbackBounds.start)}–{rootStamp(playbackBounds.end)}</p>:null}</div>
        <button className="root-primary" disabled={audioState==='idle'&&!rangeValid} onClick={primaryPlayback}>{audioState==='preparing'?'取消準備播放':audioState==='playing'?'暫停播放':'播放原曲範圍'}</button>
        <label><input type="checkbox" aria-label="循環原曲範圍" checked={rangeLoop} onChange={e=>{if(scope==='range')player.stop();setRangeLoop(e.target.checked);}}/>A–B 循環</label>
        <span aria-label="目前播放聲音">{audioState==='idle'?'已暫停 · 下次播放原曲':mode==='source'?'原曲':scope==='whole'||scope==='range'?'原曲＋已採用根音（回顧）':mode==='root'?'比較音':'原曲＋比較音'}{metronomeActive?'＋節拍聲':''}</span>
      </section>
      {doc.grid&&gridChanged?<div role="alert" aria-label="拍格需要確認" className="root-problem">拍格已改動，採用前請預覽並套用分段。<button onClick={()=>{showTools(true);toolsPanel.current?.scrollIntoView({block:'nearest'});}}>調整並套用拍格</button></div>:null}
      <div className="root-workspace">
      <RootSpectrogram key={`spectrum-${doc.source.fingerprint}`} document={doc} api={api} position={position} playing={audioState==='playing'} range={range} grid={gridSettings}
        onSeek={seekVisual} onRange={(start,end)=>editRange(String(start),String(end))}
        onPlay={playVisualRange} onPause={()=>player.stop()} onUseSelectedRange={()=>{if(segment)editRange(String(segment.start),String(segment.end));}} selectedId={selected} playbackControls={toolsOpen}/>
      <section className="root-listen" aria-label="當段聽辨">
        <div className="root-segment-heading"><h2 aria-label="目前判斷段落">目前判斷：{doc.grid?rootSegmentLabel(doc,segment):`第 ${index+1} 段`} <small>{rootStamp(segment.start)}–{rootStamp(segment.end)}</small></h2><div><button disabled={visibleIndex<=0} onClick={()=>chooseSegment(visibleSegments[visibleIndex-1].s.id)}>上一段</button><button disabled={visibleIndex<0||visibleIndex===visibleSegments.length-1} onClick={()=>chooseSegment(visibleSegments[visibleIndex+1].s.id)}>下一段</button></div></div>
        {scope!=='segment'&&playingSegment?<p className="root-range-current" aria-label="連聽目前區段">播放游標：第 {playingIndex+1} 段 · {scope==='locate'||mode==='source'?'只有原曲':playingSegment.status==='confirmed'&&playingSegment.root!==null?`原曲＋根音 ${ROOT_NAMES[playingSegment.root]}`:'只有原曲（根音待聽）'}</p>:null}
        <label hidden={!toolsOpen} className="root-scrubber">播放位置 <output>{rootStamp(position)}</output><input aria-label="根音練習播放位置" type="range" min={scope==='range'&&rangeValid?range.start:scope!=='segment'?0:Math.max(0,segment.start-(context ? .75 : 0))} max={scope==='range'&&rangeValid?range.end:scope!=='segment'?doc.source.duration:Math.min(doc.source.duration,segment.end+(context ? .75 : 0))} step=".01" value={position} onChange={e=>{player.stop();setPosition(Number(e.target.value));}}/></label>
        <div hidden={!toolsOpen} className="root-transport"><button className="root-primary" disabled={scope==='range'&&!rangeValid} onClick={togglePlayback}>{audioState==='preparing'?'取消準備':audioState==='playing'?'暫停':scope==='range'?'播放範圍':scope==='whole'?'播放行進':scope==='locate'?'播放原曲':'播放這段'}</button><button onClick={()=>{setMode('source');play(trial,'source');}}>聽原曲</button><label>聲音 <select aria-label="根音練習聲音" disabled={scope!=='segment'} value={scope==='segment'||scope==='range'?mode:scope==='locate'?'source':'mix'} onChange={e=>{player.stop();setMode(e.target.value as RootAudioMode);}}><option value="mix">原曲＋根音</option><option value="source">原曲</option><option value="root">根音</option></select></label></div>
        <div hidden={!toolsOpen} className="root-options"><label><input type="checkbox" disabled={scope!=='segment'} checked={loop} onChange={e=>{player.stop();setLoop(e.target.checked);}}/>循環這段</label><label><input type="checkbox" disabled={scope!=='segment'} checked={context} onChange={e=>{player.stop();setContext(e.target.checked);}}/>聽一點前後文</label><label><input type="checkbox" checked={hideClues} onChange={e=>setHideClues(e.target.checked)}/>先自己聽，隱藏參考音</label></div>
        <div className="root-clues">
          <div className="root-clue-title"><h3>{hideClues?'先自己試試':'三個參考音'}</h3><span>點音名試聽，不會改稿</span></div>
          {!hideClues?<>
            <div className="root-candidates" aria-label="參考音，由低到高">{[...candidates].sort((a,b)=>rootAuditionMidi(a.pitch_class)-rootAuditionMidi(b.pitch_class)).map(c=><button type="button" key={c.pitch_class} data-root={c.pitch_class} aria-label={`參考音 ${rootAuditionName(c.pitch_class)}`} aria-pressed={trial===rootAuditionMidi(c.pitch_class)} onClick={()=>audition(rootAuditionMidi(c.pitch_class))}><strong>{rootAuditionName(c.pitch_class)}</strong><span>試聽</span></button>)}</div>
            <p className="root-clue-message">{clueMessage}</p>
            {evidence.state!=='ready'?<div className="root-evidence"><span role="status">{evidence.message}</span>{candidateBusy?<button disabled={evidence.state==='cancelling'} onClick={()=>void refreshEvidence('DELETE')}>取消準備參考音</button>:<button disabled={evidence.state==='unavailable'||evidence.state==='loading'} onClick={()=>void refreshEvidence('POST')}>準備參考音</button>}</div>:null}
          </>:<p>先聽原曲，再從下方音高中比較。取消勾選即可看線索。</p>}
          <p className="root-register">由低到高排列 · E2 是吉他第六弦空弦音；試聽範圍 Eb2–Eb3。</p>
          <details open={hideClues||candidates.length===0} className="root-other"><summary>其他音（Eb2–Eb3）</summary><div className="root-pitch-grid">{ROOT_AUDITION_ORDER.map(p=><button type="button" key={p} aria-label={`試聽 ${auditionMidiName(p)}`} aria-pressed={trial===p} onClick={()=>audition(p)}>{auditionMidiName(p)}</button>)}</div></details>
          <p className="root-current" aria-live="polite">{trial===null?'尚未選擇試聽音':`目前試聽 ${auditionMidiName(trial)}${segment.status==='confirmed'&&segment.root===trial%12?' · 已採用':' · 尚未採用'}`}</p>
          <div className="root-pitch-steps"><button type="button" disabled={trial===null||trial<=ROOT_AUDITION_MIN} onClick={()=>stepPitch(-1)}>低半音</button><button type="button" disabled={trial===null||trial>=ROOT_AUDITION_MAX} onClick={()=>stepPitch(1)}>高半音</button><small>逐音比較，採用才保存。</small></div>
          <p id="root-adoption-target" aria-label="採用目標" className="root-adoption-target">將記錄到 {doc.grid?rootSegmentLabel(doc,segment):`第 ${index+1} 段`} · {rootStamp(segment.start)}–{rootStamp(segment.end)}</p>
          <div className="root-decide" aria-describedby="root-adoption-target"><button className="root-primary" disabled={!editable||trial===null||!!doc.grid&&gridChanged} onClick={()=>decision(trial===null?null:trial%12,'confirmed')}>採用這個根音</button><button disabled={!editable||!!doc.grid&&gridChanged} onClick={()=>decision(null,'unsure')}>還聽不出來</button></div>
        </div>
        <div className="root-volumes"><label>原曲音量 <input aria-label="練習原曲音量" type="range" min="0" max="1" step=".01" value={sourceVolume} onChange={e=>setSourceVolume(Number(e.target.value))}/></label><label>根音音量 <input aria-label="練習根音音量" type="range" min="0" max="1" step=".01" value={rootVolume} onChange={e=>setRootVolume(Number(e.target.value))}/></label></div>
        <small className="root-explanation">選音後持續發聲，循環時也不中斷；換音或暫停即停止舊音。前後文也會持續試聽音。根音指和聲根音，例如 C/E 的 C；不是最低音。採用只記音名，試聽八度不代表原曲八度。</small>
        {notice?<p className="root-notice" role="status">{notice}</p>:null}
      </section>
      </div>
      <div className="root-finish"><button disabled={!editable||!sheet.canUndo} onClick={()=>history(true)}>復原</button><button disabled={!editable||!sheet.canRedo} onClick={()=>history(false)}>重做</button><button onClick={()=>play(null,'mix','whole')}>回顧我的行進（含已採用根音）</button>{(scope==='range'||scope==='whole')?<span>{scope==='range'?'範圍':'整首'}連聽：{mode==='source'?'只播放原曲':'待聽處只播放原曲'}</span>:null}</div>
      <details ref={toolsPanel} className="root-advanced root-tools" open={toolsOpen} onToggle={e=>showTools(e.currentTarget.open)}>
        <summary>練習設定與進階工具</summary>
      <RootPracticeGrid key={doc.source.fingerprint} fingerprint={doc.source.fingerprint} duration={doc.source.duration} position={position} playing={audioState==='playing'} preparing={audioState==='preparing'} locating={scope==='locate'&&audioState!=='idle'} readPosition={()=>audioState==='playing'?player.read():position} onSeek={time=>{player.stop();setPosition(time);setScope('locate');}} onLocate={locateRange} onRange={(start,end)=>editRange(String(start),String(end))} onGrid={setMetronome} onSettings={updateGridSettings} initialGrid={doc.grid} range={range}/>
      <section className="root-segmentation" aria-label="小節分段">
        <h2>以小節抓根音</h2><p>{gridChanged?'拍格尚未套用到分段。請預覽並套用後開始逐段聽辨。':'每小節一段；小節內有換根音線索時，才細分為半／四分之一小節。'}</p>
        <div className="root-grid-actions"><button disabled={!editable||!gridSettings||planBusy} onClick={()=>void previewSegments()}>{planBusy?'正在檢查小節內換音…':'預覽小節分段'}</button><button disabled={!editable||!gridSettings} onClick={previewWholeBars}>只按整小節重排</button></div>
        {planNotice?<p role="status">{planNotice}</p>:null}
        {plan?<div ref={planPanel} className="root-segment-preview" role="region" aria-label="分段預覽"><p>{plan.note}</p><p>原 {doc.segments.length} 段 → {plan.document.segments.length} 段；延用 {plan.preserved} 段根音，{plan.review.length} 段需重新確認。</p>
          {plan.exceptions.length?<details open><summary>{plan.exceptions.length} 個小節有自動細分建議</summary><ul>{plan.exceptions.map(e=><li key={e.bar}>第 {e.bar} 小節 · {e.parts} 段 · {rootStamp(e.start)}–{rootStamp(e.end)}</li>)}</ul></details>:<p>沒有自動細分建議。{!plan.evidence_available?'未使用音訊線索。':''}</p>}
          {plan.review.length?<details open><summary>保留待確認的原判斷</summary><ul>{plan.review.map((r,i)=><li key={i}>{rootStamp(r.start)}–{rootStamp(r.end)}：原採用 {r.roots.map(r=>ROOT_NAMES[r]).join('、')}，新段先保留待聽。</li>)}</ul></details>:null}
          <div className="root-grid-actions"><button className="root-primary" disabled={!editable||plan.base!==JSON.stringify(doc)} onClick={applyPlan}>套用這份分段</button><button onClick={()=>setPlan(null)}>取消預覽</button></div></div>:null}
      </section>
      <section className="root-range" aria-label="範圍連聽">
        <h2>選擇播放範圍</h2><p>拖動 A 起點、B 終點，或聽原曲時按下方按鈕設定位置。</p>
        <div className="root-range-locate"><button onClick={locateRange}>{scope==='locate'&&audioState!=='idle'?'暫停原曲定位':'聽原曲找起終點'}</button><span>目前位置 <output aria-label="定位目前時間">{rootStamp(position)}</output></span></div>
        <div className="root-range-endpoints">
          <div><div className="root-endpoint-heading"><strong>A 起點</strong><output>{Number.isFinite(range.start)?rootStamp(range.start):'未設定'}</output></div><input aria-label="拖曳範圍起點" aria-valuetext={Number.isFinite(range.start)?rootStamp(range.start):'未設定'} type="range" min="0" max={doc.source.duration} step=".01" value={Number.isFinite(range.start)?range.start:0} onChange={e=>dragBoundary('start',Number(e.target.value))}/><label>秒數 <input aria-label="連聽起點秒數" type="number" min="0" max={doc.source.duration} step=".01" value={rangeStart} onChange={e=>editRange(e.target.value,rangeEnd)}/></label><button disabled={audioState==='preparing'} onClick={()=>markBoundary('start')}>目前位置設為起點</button></div>
          <div><div className="root-endpoint-heading"><strong>B 終點</strong><output>{Number.isFinite(range.end)?rootStamp(range.end):'未設定'}</output></div><input aria-label="拖曳範圍終點" aria-valuetext={Number.isFinite(range.end)?rootStamp(range.end):'未設定'} type="range" min="0" max={doc.source.duration} step=".01" value={Number.isFinite(range.end)?range.end:doc.source.duration} onChange={e=>dragBoundary('end',Number(e.target.value))}/><label>秒數 <input aria-label="連聽終點秒數" type="number" min="0" max={doc.source.duration} step=".01" value={rangeEnd} onChange={e=>editRange(rangeStart,e.target.value)}/></label><button disabled={audioState==='preparing'} onClick={()=>markBoundary('end')}>目前位置設為終點</button></div>
        </div>
        {rangeNotice?<p role="status">{rangeNotice}</p>:null}
        <div className="root-range-actions"><button className="root-primary" disabled={!rangeValid} onClick={toggleRange}>{scope==='range'&&audioState!=='idle'?'暫停範圍':'播放選取範圍'}</button><label><input type="checkbox" checked={rangeLoop} onChange={e=>{if(scope==='range')player.stop();setRangeLoop(e.target.checked);}}/>循環選取範圍</label><span>{rangeValid?`${rootStamp(range.start)}–${rootStamp(range.end)}`:'請設定有效起訖'}</span></div>
        <p>{scope==='range'&&mode==='source'?'目前範圍只播放原曲。':'已採用根音的地方一起播放，其他地方只有原曲。'}</p>
        <details><summary>按段落選起終點</summary><div className="root-range-bounds">
          <div><label>從 <select aria-label="連聽起始段" value={doc.segments.find(s=>s.start===range.start)?.id??'custom'} onChange={e=>rangeBoundary('start',doc.segments.findIndex(s=>s.id===e.target.value))}><option value="custom" disabled>自訂時間</option>{doc.segments.map((s,i)=><option key={s.id} value={s.id}>第 {i+1} 段 · {rootStamp(s.start)}</option>)}</select></label><button onClick={()=>rangeBoundary('start',index)}>設這段為起點</button></div>
          <div><label>到 <select aria-label="連聽結束段" value={doc.segments.find(s=>s.end===range.end)?.id??'custom'} onChange={e=>rangeBoundary('end',doc.segments.findIndex(s=>s.id===e.target.value))}><option value="custom" disabled>自訂時間</option>{doc.segments.map((s,i)=><option key={s.id} value={s.id}>第 {i+1} 段 · {rootStamp(s.end)}</option>)}</select></label><button onClick={()=>rangeBoundary('end',index)}>設這段為終點</button></div>
        </div></details>
        {!rangeValid?<p role="alert">起點須早於終點至少 0.08 秒，且都在歌曲範圍內。</p>:null}
      </section>
      {doc.grid?<section className="root-tools" aria-label="目前小節細分"><h3>目前小節細分</h3><p>通常整小節一個根音；若小節內換音，可按拍細分，或改回整小節。</p><div className="root-grid-actions"><button disabled={!editable||gridChanged} onClick={()=>previewSubdivision(1)}>整小節一段</button><button disabled={!editable||gridChanged||doc.grid.beats%2!==0} onClick={()=>previewSubdivision(2)}>半小節一段</button><button disabled={!editable||gridChanged||doc.grid.beats%4!==0} onClick={()=>previewSubdivision(4)}>四分之一小節一段</button></div></section>:<details className="root-tools"><summary>段落調整</summary><p>換音位置不對時，在想切開的地方暫停；也可以拖動播放位置。調整後相關區段會改為待聽，原和弦譜不變。</p><button disabled={!editable||position-segment.start<.08||segment.end-position<.08} onClick={()=>structure('split')}>從游標處分成兩段</button><button disabled={!editable||index===doc.segments.length-1} onClick={()=>structure('merge')}>與下一段合併</button></details>}
      </details>
      <details className="root-tools"><summary>歷次保存</summary><p>重新分段前的判斷保存在這裡，可下載原稿或預覽恢復。</p><button onClick={()=>void loadArchives()}>載入歷次保存</button>{historyNotice?<p role="status">{historyNotice}</p>:null}{archives.map(a=><div key={a.version}>版本 {a.version} · {a.document.segments.length} 段 <button onClick={()=>download(JSON.stringify(a.document,null,2),`root-practice-${job}-v${a.version}.json`)}>下載版本 {a.version}</button><button disabled={!editable} onClick={()=>restoreArchive(a.document)}>預覽恢復版本 {a.version}</button></div>)}</details>
      <details className="root-tools"><summary>進度與備份</summary><p>進度自動保存於這首來源的共用練習空間；受邀者共用，並非私人帳號。備份只包含根音與時間，不含音訊。</p><button onClick={()=>download(JSON.stringify(doc,null,2),`root-practice-${job}.json`)}>下載完整練習</button><button onClick={()=>download(rootText(doc),`root-progression-${job}.txt`,'text/plain')}>下載根音行進文字</button><label className="root-import">還原同曲備份 <input aria-label="還原根音備份" disabled={!editable} type="file" accept=".json,application/json" onChange={e=>{const file=e.target.files?.[0];if(file)void importBackup(file);e.target.value='';}}/></label>{doc.source.source_start>0?<p>本頁 0 秒對應原曲 {rootStamp(doc.source.source_start)}，時間不必再次偏移。</p>:null}</details>
    </>:<p>載入後即可選段練習。</p>}
  </main>;
}
