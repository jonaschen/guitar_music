import {useEffect,useRef,useState} from 'react';
import {rootStamp} from './rootPracticeDocument';
import {rootBarAt,rootBarLength,rootBeatLength,rootNearbyBars,validRootGrid,type RootGrid} from './rootPracticeGrid';

type Preferences={bpm:string;beats:string;anchor:string;click:boolean};
export function RootPracticeGrid({fingerprint,duration,position,playing,preparing,locating,readPosition,onSeek,onLocate,onRange,onGrid,onSettings,initialGrid,range}:{
  fingerprint:string;duration:number;position:number;playing:boolean;preparing:boolean;locating:boolean;readPosition:()=>number;
  onSeek:(time:number)=>void;onLocate:()=>void;onRange:(start:number,end:number)=>void;onGrid:(grid:RootGrid|null)=>void;onSettings:(grid:RootGrid|null)=>void;initialGrid?:RootGrid|null;range:{start:number;end:number};
}){
  const key=`guitarscribe.root-grid.${fingerprint}`;
  const [prefs,setPrefs]=useState<Preferences>(()=>{
    const fallback={bpm:String(initialGrid?.bpm??115),beats:String(initialGrid?.beats??4),anchor:String(initialGrid?.anchor??0),click:false};
    try{const saved=JSON.parse(localStorage.getItem(key)??'null');if(saved&&validRootGrid(saved,duration))return initialGrid?{...fallback,click:saved.click===true}:{bpm:String(saved.bpm),beats:String(saved.beats),anchor:String(saved.anchor),click:saved.click===true};}catch{/* Optional local preference. */}
    return fallback;
  });
  const [storageFailed,setStorageFailed]=useState(false);
  const ruler=useRef<HTMLElement|null>(null);
  const grid={bpm:Number(prefs.bpm),beats:Number(prefs.beats),anchor:Number(prefs.anchor)};
  const valid=!!prefs.bpm.trim()&&!!prefs.beats.trim()&&!!prefs.anchor.trim()&&validRootGrid(grid,duration);
  const length=valid?rootBarLength(grid):0,bars=valid?rootNearbyBars(grid,position,duration):[],current=valid?rootBarAt(grid,position,duration):null;
  useEffect(()=>{if(initialGrid)setPrefs(p=>({...p,bpm:String(initialGrid.bpm),beats:String(initialGrid.beats),anchor:String(initialGrid.anchor)}));},[initialGrid?.bpm,initialGrid?.beats,initialGrid?.anchor]);
  useEffect(()=>{
    onSettings(valid?grid:null);
    onGrid(valid&&prefs.click?grid:null);
    if(valid)try{localStorage.setItem(key,JSON.stringify({...grid,click:prefs.click}));setStorageFailed(false);}catch{setStorageFailed(true);}
  },[prefs.bpm,prefs.beats,prefs.anchor,prefs.click,valid,key,onGrid,onSettings]);
  useEffect(()=>{
    const nav=ruler.current;if(!nav)return;
    const center=()=>{const button=nav.querySelector<HTMLElement>('[aria-current="step"]');if(button){const n=nav.getBoundingClientRect(),b=button.getBoundingClientRect();nav.scrollLeft+=b.left-n.left-(n.width-b.width)/2;}};
    center();const observer=new ResizeObserver(center);observer.observe(nav);return()=>observer.disconnect();
  },[current?.index,valid]);
  const change=(name:keyof Preferences,value:string|boolean)=>setPrefs(p=>({...p,[name]:value}));
  const anchor=(time:number)=>change('anchor',String(Math.max(0,Math.min(duration,Math.round(time*1000)/1000))));
  return <section className="root-grid" aria-label="節拍與小節對齊">
    <h2>節拍與小節對齊</h2>
    <div className="root-grid-settings">
      <label>節拍器 BPM<input aria-label="節拍器 BPM" type="number" min="20" max="300" step=".1" value={prefs.bpm} onChange={e=>change('bpm',e.target.value)}/></label>
      <label>每小節幾拍<input aria-label="每小節幾拍" type="number" min="1" max="12" step="1" value={prefs.beats} onChange={e=>change('beats',e.target.value)}/></label>
      <output aria-label="小節長度">{valid?`每拍 ${rootBeatLength(grid).toFixed(3)} 秒 · 每小節 ${length.toFixed(3)} 秒`:'請設定有效的節拍與對齊點'}</output>
    </div>
    <label className="root-grid-position">全曲定位 <output>{rootStamp(position)}</output><input aria-label="小節對齊全曲定位" type="range" min="0" max={duration} step=".001" value={position} onChange={e=>onSeek(Number(e.target.value))}/></label>
    <div className="root-grid-actions"><button onClick={onLocate}>{locating?'暫停對拍':'播放原曲對拍'}</button><button disabled={preparing} onClick={()=>anchor(readPosition())}>目前位置設為小節起點</button><label><input type="checkbox" checked={prefs.click} onChange={e=>change('click',e.target.checked)}/>播放時加入節拍聲</label></div>
    <div className="root-grid-anchor"><label>小節對齊點（秒）<input aria-label="小節對齊點秒數" type="number" min="0" max={duration} step=".001" value={prefs.anchor} onChange={e=>change('anchor',e.target.value)}/></label><span>整組小節一起平移</span></div>
    <div className="root-grid-actions">
      <button disabled={!valid||grid.anchor<=0} onClick={()=>anchor(grid.anchor-rootBeatLength(grid))}>提前一拍</button>
      <button disabled={!valid||grid.anchor<=0} onClick={()=>anchor(grid.anchor-.01)}>提前 10 ms</button>
      <button disabled={!valid||grid.anchor>=duration} onClick={()=>anchor(grid.anchor+.01)}>延後 10 ms</button>
      <button disabled={!valid||grid.anchor>=duration} onClick={()=>anchor(grid.anchor+rootBeatLength(grid))}>延後一拍</button>
    </div>
    {!valid?<p role="alert">BPM 請填 20–300，每小節 1–12 拍；對齊點須在歌曲內。</p>:<>
      <p>點小節可選為 A／B 播放範圍。格線向歌曲前後延伸。</p>
      <nav ref={ruler} className="root-bar-ruler" aria-label="附近小節">{bars.map(bar=><button key={bar.index} aria-current={current?.index===bar.index?'step':undefined} aria-label={`選取第 ${bar.number} 小節${bar.partial?'（不完整）':''}`} aria-pressed={Math.abs(range.start-bar.start)<1e-7&&Math.abs(range.end-bar.end)<1e-7} data-playing={playing&&current?.index===bar.index} disabled={bar.end-bar.start<.08} onClick={()=>onRange(bar.start,bar.end)}>
        <strong>第 {bar.number} 小節</strong><span className="root-bar-ticks" aria-hidden="true">{Array.from({length:grid.beats},(_,i)=><i key={i} data-active={playing&&current?.index===bar.index&&Math.floor((position-bar.rawStart)/rootBeatLength(grid)+1e-7)===i}>{i+1}</i>)}</span>
        <small>{rootStamp(bar.start)}–{rootStamp(bar.end)}</small><small>{bar.partial?'不足一小節':'選取這小節'}</small>
      </button>)}</nav>
    </>}
    <p className="root-grid-hint">對齊點是你指定的第 1 拍。小節編號從歌曲開頭依序計算；設定存在此瀏覽器。調整後按「預覽小節分段」檢查，再套用到根音稿。</p>
    {storageFailed?<p role="status">瀏覽器無法保存對拍設定，關閉此頁後可能需要重新設定。</p>:null}
  </section>;
}
