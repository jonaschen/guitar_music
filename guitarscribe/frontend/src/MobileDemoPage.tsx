import {useEffect,useRef,useState} from 'react';
import {RootSpectrogram} from './RootSpectrogram';
import {parseRootDocument,ROOT_NAMES,rootStamp,type RootDocument} from './rootPracticeDocument';
import {parseStructure,type StructureDocument} from './songStructureDocument';
import './mobileDemo.css';
type Range={start:number;end:number};
export function mobileDemoUrl(job:string){const url=new URL(location.pathname,location.origin);url.searchParams.set('practice','demo');url.searchParams.set('job',job);return url.pathname+url.search;}
export function MobileDemoPage({job,api,title}:{job:string;api:string;title:string}){
 const [structure,setStructure]=useState<StructureDocument|null>(null),[roots,setRoots]=useState<RootDocument|null>(null),[candidate,setCandidate]=useState(false),[error,setError]=useState(''),[loading,setLoading]=useState(true),[reload,setReload]=useState(0);
 const [step,setStep]=useState(1),[visual,setVisual]=useState(false),[selected,setSelected]=useState(''),[position,setPosition]=useState(0),[range,setRange]=useState<Range>({start:0,end:0}),[playing,setPlaying]=useState(false),[loop,setLoop]=useState(false),[notice,setNotice]=useState('');
 const audio=useRef<HTMLAudioElement|null>(null),bounds=useRef<Range|null>(null),seek=useRef<number|null>(null),generation=useRef(0),alive=useRef(true);
 const endpoint=`${api}/api/v1/jobs/${encodeURIComponent(job)}`;
 const section=structure?.sections.find(s=>s.id===selected)??structure?.sections[0];
 const rootId=roots?.segments.find(r=>r.start<=position&&r.end>position)?.id??roots?.segments[0].id??'';
 const audioUrl=structure?`${endpoint}/song-structure/audio?fingerprint=${structure.source.fingerprint}&audio_sha256=${structure.source.audio_sha256}`:undefined;
 function stop(){generation.current++;audio.current?.pause();setPlaying(false);seek.current=null;}
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++;audio.current?.pause();};},[]);
 useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');setStructure(null);setRoots(null);stop();
 void(async()=>{try{
  const response=await fetch(endpoint+'/song-structure',{signal:controller.signal});if(!response.ok)throw Error('目前無法讀取歌曲結構，請稍後重試。');const saved=await response.json();
  if(saved.job_id!==job||!saved.source_matches||!saved.current_source)throw Error('歌曲或錄音來源已變動，請回練習頁核對後再介紹。');
  let draft=saved.document,isCandidate=false;
  if(!draft){const reply=await fetch(endpoint+'/song-structure/analysis',{signal:controller.signal});if(!reply.ok)throw Error('這首歌尚未備妥結構初稿，請先從練習頁分析。');const analysis=await reply.json();if(analysis.job_id!==job||analysis.state!=='ready')throw Error('這首歌的結構初稿尚未完成，請先在練習頁準備，再開啟介紹。');draft=analysis.candidate;isCandidate=true;}
  const document=parseStructure(JSON.stringify(draft),saved.current_source);if(document.source.job_id!==job)throw Error('歌曲來源不符。');
  const reply=await fetch(endpoint+'/root-practice',{signal:controller.signal});if(!reply.ok)throw Error('根音練習暫時無法讀取，請稍後重試。');const root=await reply.json();const {audio_sha256:_,...source}=document.source;
  if(root.job_id!==job)throw Error('根音來源不符。');const parsed=parseRootDocument(JSON.stringify(root.document),source);
  if(controller.signal.aborted)return;setStructure(document);setRoots(parsed);setCandidate(isCandidate);const first=document.sections.find(s=>!['start','end','unknown'].includes(s.label))??document.sections[0];setSelected(first.id);setRange(first);setPosition(first.start);
 }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'介紹內容暫時無法載入。');}finally{if(!controller.signal.aborted)setLoading(false);}})();return()=>controller.abort();},[endpoint,reload]);
 useEffect(()=>{function hidden(){if(window.document.hidden){stop();setNotice('已暫停。回來後按播放即可繼續介紹。');}}function leave(){stop();}window.document.addEventListener('visibilitychange',hidden);window.addEventListener('pagehide',leave);return()=>{window.document.removeEventListener('visibilitychange',hidden);window.removeEventListener('pagehide',leave);};},[]);
 useEffect(()=>{if(!playing)return;const timer=setInterval(()=>{const a=audio.current;if(!a)return;setPosition(a.currentTime);if(bounds.current&&a.currentTime>=bounds.current.end){if(loop&&!window.document.hidden){a.currentTime=bounds.current.start;}else{a.pause();setPlaying(false);}}},50);return()=>clearInterval(timer);},[playing,loop]);
 function play(next=range){const a=audio.current;if(!a||!structure||next.start<0||next.end>structure.source.duration||next.end-next.start<.08)return;stop();const ticket=generation.current;bounds.current=next;seek.current=next.start;setRange(next);setPosition(next.start);setNotice('');if(a.readyState>=1){a.currentTime=next.start;seek.current=null;}
  // Call play inside the tap gesture, before any network/metadata await.
  void a.play().catch(e=>{if(alive.current&&ticket===generation.current&&e.name!=='AbortError')setNotice('原曲暫時無法播放；請確認連線後再按一次播放。');});
 }
 function changeStep(next:number){stop();setNotice('');setStep(next);if(next===3)setVisual(true);window.scrollTo({top:0,behavior:'instant'});}
 function choose(id:string){const s=structure?.sections.find(s=>s.id===id);if(!s)return;stop();setSelected(id);setRange(s);setPosition(s.start);}
 const practice=new URL(location.pathname,location.origin);practice.searchParams.set('practice','roots');practice.searchParams.set('visual','1');practice.searchParams.set('job',job);
 async function copy(){try{await navigator.clipboard.writeText(new URL(mobileDemoUrl(job),location.origin).href);setNotice('已複製介紹連結；換裝置仍須使用原有登入。');}catch{setNotice('可直接從瀏覽器網址列複製目前連結。');}}
 return <main className="mobile-demo" aria-label="手機介紹"><header className="md-header"><span>GuitarScribe · 手機介紹</span><a href={practice.pathname+practice.search}>回到練習</a></header><h1>{title}</h1><p className="md-lead">先看歌曲的大段，再聽一小段，最後看低頻如何移動。</p><p className="md-readonly">介紹模式只查看與播放，不修改練習進度。</p>
 {loading?<p role="status">正在準備介紹內容…</p>:error?<section role="alert"><p>{error}</p><button onClick={()=>setReload(v=>v+1)}>重新載入</button></section>:structure&&roots&&section?<>
 <nav className="md-steps" aria-label="介紹步驟">{['歌曲結構','聽一段','看低頻'].map((name,i)=><button key={name} aria-current={step===i+1?'step':undefined} onClick={()=>changeStep(i+1)}>{i+1}. {name}</button>)}</nav>
 <section hidden={step!==1} aria-label="介紹歌曲結構"><h2>整首歌先分成 {structure.sections.length} 個大段</h2><p>這些是前奏、主歌、副歌等歌曲段落。選一段，就不必一次面對 {roots.segments.length} 個根音區段。</p>{candidate?<p className="md-note">展示的是分析初稿，尚未套用。</p>:null}<p>名稱與交界可以分開核對；待確認的標示會保留。</p><div className="md-sections">{structure.sections.map((s,i)=><button key={s.id} aria-label={`介紹第 ${i+1} 段 ${s.display_label}`} aria-pressed={section.id===s.id} onClick={()=>choose(s.id)}><strong>{i+1}. {s.display_label}</strong><span>{rootStamp(s.start)}–{rootStamp(s.end)}</span><small>{s.name_review_status==='user_confirmed'?'名稱已確認':s.name_review_status==='user_corrected'?'名稱已修改':'名稱待確認'} · {s.boundary_review_status==='user_confirmed'?'邊界已確認':'邊界待確認'}</small></button>)}</div><button className="md-primary" onClick={()=>changeStep(2)}>下一步：聽這一段</button></section>
 <section hidden={step!==2} aria-label="介紹原曲回聽"><h2>一次只練一段</h2><p>用原曲聽換和弦的位置，反覆練同一小段。這裡不加入合成根音或和弦聲音。</p><label>介紹段落<select aria-label="介紹段落" value={section.id} onChange={e=>choose(e.target.value)}>{structure.sections.map((s,i)=><option key={s.id} value={s.id}>{i+1}. {s.display_label} {rootStamp(s.start)}</option>)}</select></label><p className="md-note">{section.display_label} · {rootStamp(section.start)}–{rootStamp(section.end)}</p><button className="md-primary" onClick={()=>play(section)}>播放選定段落</button><button onClick={stop}>暫停原曲</button><p>例如可以這樣介紹：「我先聽這段，再看低頻線條，自己判斷根音。」</p><button className="md-primary" onClick={()=>changeStep(3)}>下一步：看低頻圖</button></section>
 <section hidden={step!==3} aria-label="介紹低頻視覺化"><h2>看線條，再用耳朵確認</h2><p>按「產生低頻圖」，再點圖移動時間；可用 A、B 標記圈選想聽的範圍。手機網路首次載入整首音訊可能較慢。</p>{visual?<RootSpectrogram document={roots} api={api} audioUrl={audioUrl} initialOpen presentation position={position} playing={playing} range={range} grid={null} selectedId={rootId} playbackControls onSeek={time=>{stop();setPosition(time);}} onRange={(start,end)=>{stop();setRange({start,end});}} onPlay={(start,end)=>play({start,end})} onPause={stop} onUseSelectedRange={()=>{stop();setRange(section);setPosition(section.start);}}/>:null}<p>亮線可能是基音、泛音或鼓聲，並非自動判定的正確根音。</p><p>這段已採用的根音：{roots.segments.filter(r=>r.start<section.end&&r.end>section.start&&r.status==='confirmed'&&r.root!==null).map(r=>ROOT_NAMES[r.root!]).join(' → ')||'尚未記錄；未知處保持待聽。'}</p></section>
 <div className="md-player" hidden={step===1}><span>{rootStamp(range.start)}–{rootStamp(range.end)} · 原曲</span><button onClick={()=>playing?stop():play(range)}>{playing?'暫停介紹播放':'播放目前範圍'}</button><label className="md-loop"><input type="checkbox" checked={loop} onChange={e=>setLoop(e.target.checked)}/> A–B 循環</label><audio ref={audio} playsInline preload="metadata" src={audioUrl} onLoadedMetadata={()=>{if(seek.current!==null&&audio.current){audio.current.currentTime=seek.current;seek.current=null;}}} onPlaying={()=>{if(window.document.hidden){stop();return;}setPlaying(true);}} onPause={()=>setPlaying(false)} onEnded={()=>{setPlaying(false);if(loop&&bounds.current&&!window.document.hidden)play(bounds.current);}} onError={()=>setNotice('音訊目前無法載入，請確認連線後再試。')}/></div>
 <footer><button onClick={()=>void copy()}>複製介紹連結</button><a href={practice.pathname+practice.search}>結束介紹，回到練習</a><p>請使用自己的邀請登入。手機介紹不需要重新分析歌曲。</p></footer>
 </>:null}{notice?<p role="status" className="md-notice">{notice}</p>:null}</main>;
}
