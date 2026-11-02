import {useEffect, useMemo, useState} from 'react';
import {ChordDiagram} from './ChordDiagram';
import type {SongScore} from './types';

type Voicing=NonNullable<SongScore['chords'][number]['available_voicings']>[number];

/** Read-only: looking up a fingering never edits the score or playback voicing. */
export function ChordFingerings({score,apiBase}:{score:SongScore;apiBase:string}){
  const [open,setOpen]=useState(false),[selected,setSelected]=useState('');
  const [remote,setRemote]=useState<{key:string;shape?:Voicing;error?:string}>({key:''});
  const groups=useMemo(()=>{
    const seen=new Set<string>(),counts=new Map<string,number>();
    return score.chords.flatMap(chord=>{
      if(['n','nc','n.c.','no_chord'].includes(chord.symbol.trim().toLowerCase()))return [];
      const symbol=chord.shape_symbol||chord.symbol;
      const stored=chord.available_voicings?.find(v=>v.id===chord.voicing_id)??chord.available_voicings?.[0];
      const key=JSON.stringify([symbol,stored?.id,stored?.frets]);
      if(seen.has(key))return [];seen.add(key);
      const count=(counts.get(symbol)??0)+1;counts.set(symbol,count);
      return [{key,symbol,stored,label:count===1?symbol:`${symbol}（按法 ${count}）`}];
    });
  },[score.chords]);
  const group=groups.find(g=>g.key===selected)??groups[0];
  const capo=score.analysis.capo;
  const stored=group?.stored?.capo===capo?group.stored:undefined;
  const standard=score.guitar.tuning.join(',')==='40,45,50,55,59,64';
  const requestKey=JSON.stringify([group?.symbol,capo,score.guitar.max_fret,standard]);
  useEffect(()=>{
    if(!open||!group||stored||!standard)return;
    const controller=new AbortController();let active=true;
    setRemote({key:requestKey});
    const query=new URLSearchParams({symbol:group.symbol,capo:String(capo),max_fret:String(score.guitar.max_fret)});
    void fetch(`${apiBase}/chord-voicings?${query}`,{signal:controller.signal})
      .then(async r=>{if(!r.ok)throw Error();return await r.json() as Voicing[];})
      .then(shapes=>{if(active)setRemote({key:requestKey,shape:shapes[0],error:shapes.length?undefined:'目前沒有這個和弦的按法資料。'});})
      .catch(()=>{if(active)setRemote({key:requestKey,error:'暫時無法載入按法，請收合後重新開啟。'});});
    return ()=>{active=false;controller.abort();};
  },[open,group?.symbol,stored,standard,requestKey,apiBase,capo,score.guitar.max_fret]);
  const shape=stored??(remote.key===requestKey?remote.shape:undefined);
  const complete=shape&&shape.frets.length===6&&!shape.tags.includes('incomplete');
  const message=!group?'這份譜還沒有和弦。':!standard&&!stored?'這個調弦尚無按法資料。':shape&&!complete?'目前沒有這個和弦的完整按法。':remote.key===requestKey&&remote.error?remote.error:'正在載入按法…';
  return <details className="chord-fingerings" onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>和弦按法</summary>
    {open?<div className="chord-fingerings-content">
      {group?<label>查看和弦 <select aria-label="查看和弦按法" value={group.key} onChange={e=>setSelected(e.target.value)}>{groups.map(g=><option key={g.key} value={g.key}>{g.label}</option>)}</select></label>:null}
      {complete?<><ChordDiagram frets={shape.frets} baseFret={shape.base_fret} label={group.symbol}/>
        <p aria-label="和弦品格">品格：{shape.frets.map(f=>f===null?'×':f).join(' · ')}</p>
        <p>由左至右：第 6 弦（粗）→ 第 1 弦（細）。○ 是空弦，× 不彈。</p>
        <p>{capo?`Capo 第 ${capo} 品；圖中品格從移調夾起算。`:'未使用 Capo；圖中品格從琴枕起算。'}</p>
      </>:<p role="status">{message}</p>}
    </div>:null}
  </details>;
}
