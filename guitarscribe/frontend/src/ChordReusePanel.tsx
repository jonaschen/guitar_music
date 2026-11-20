import {useEffect,useRef,useState} from 'react';
import type {useChordPractice} from './useChordPractice';
import type {TimeRange} from './chordPracticeDocument';
import {rootStamp} from './rootPracticeDocument';
type Sheet=ReturnType<typeof useChordPractice>;
type Row={id:string;start:number;end:number;symbol:string|null;status:'fillable'|'already_same'|'target_protected'|'source_unknown'};
type Plan={plan_id:string;version:number;request:unknown;rows:Row[];can_apply:boolean};
type Operation={id:string;created_at:string;can_undo:boolean;status:string;changes:unknown[]};
const labels={fillable:'可沿用',already_same:'已相同，保留',target_protected:'已填寫，保留',source_unknown:'來源待聽，不填入'};
export function ChordReusePanel({api,job,sheet,onPlay,onStop}:{api:string;job:string;sheet:Sheet;onPlay:(range:TimeRange,section:string)=>void;onStop:()=>void}){
 const [open,setOpen]=useState(false),[sourceId,setSourceId]=useState('');
 const [start,setStart]=useState(0),[end,setEnd]=useState(0),[targetStart,setTargetStart]=useState(0);
 const [confirmed,setConfirmed]=useState(false),[plan,setPlan]=useState<Plan|null>(null),[selected,setSelected]=useState<string[]>([]);
 const [operations,setOperations]=useState<Operation[]>([]),[message,setMessage]=useState(''),[loading,setLoading]=useState(false),[refresh,setRefresh]=useState(0);
 const generation=useRef(0),alive=useRef(true),locked=sheet.lock,doc=sheet.document;
 const sources=sheet.structure?.sections.filter(s=>s.id!==locked?.section_id)??[],source=sources.find(s=>s.id===sourceId);
 const targetEnd=targetStart+end-start;
 const valid=!!source&&!!locked&&Number.isFinite(start+end+targetStart)&&start>=source.start&&end<=source.end&&end-start>=.08&&targetStart>=locked.start&&targetEnd<=locked.end;
 const ready=sheet.synced&&!sheet.busy&&!sheet.blocked;
 const endpoint=`${api}/api/v1/jobs/${encodeURIComponent(job)}/chord-practice`;
 function invalidate(){generation.current++;setPlan(null);setSelected([]);setConfirmed(false);setMessage('');onStop();}
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++;};},[]);
 useEffect(()=>{invalidate();const first=sources[0];setSourceId(first?.id??'');setStart(first?.start??0);setEnd(first?first.start+Math.min(first.end-first.start,(locked?.end??0)-(locked?.start??0)):0);setTargetStart(locked?.start??0);},[locked?.section_id,sheet.structureVersion]);
 useEffect(()=>{generation.current++;setPlan(null);setSelected([]);},[sheet.version,sheet.synced]);
 useEffect(()=>{if(!open)return;const controller=new AbortController();
  void fetch(endpoint+'/reuse-ledger',{signal:controller.signal,cache:'no-store'}).then(async r=>{
   if(!r.ok)throw Error();const data=await r.json();if(controller.signal.aborted)return;
   if(data.job_id!==job||!data.source_matches)throw Error();setOperations(data.operations);
  }).catch(()=>{if(!controller.signal.aborted)setMessage('沿用紀錄暫時無法載入；請關閉後再開啟重試。');});
  return()=>controller.abort();
 },[open,endpoint,sheet.version,refresh]);
 async function preview(){if(!valid||!ready||!doc||!locked)return;onStop();const ticket=++generation.current;setLoading(true);setPlan(null);setMessage('正在比較和弦…');
  try{const request={expected_version:sheet.version,structure_version:sheet.structureVersion,source_section_id:sourceId,target_section_id:locked.section_id,
    source_range:{start,end},target_range:{start:targetStart,end:targetEnd},fingerprint:doc.source.fingerprint,audio_sha256:doc.source.audio_sha256,alignment_confirmed:confirmed};
   const r=await fetch(endpoint+'/reuse-plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});
   if(!r.ok)throw Error(r.status===409?'和弦或結構已變動，請載入最新版本再預覽。':'範圍無法比較，請確認兩段的核心範圍。');
   const data=await r.json();if(!alive.current||ticket!==generation.current)return;
   if(data.job_id!==job||data.version!==sheet.version||data.structure_version!==sheet.structureVersion||!Array.isArray(data.rows))throw Error('預覽版本無法核對。');
   setPlan(data);setSelected(data.rows.filter((r:Row)=>r.status==='fillable').map((r:Row)=>r.id));setMessage('請檢查勾選的和弦；未勾選與已填寫的部分會保留。');
  }catch(e){if(alive.current&&ticket===generation.current)setMessage(e instanceof Error?e.message:'預覽失敗，請重試。');}
  finally{if(alive.current)setLoading(false);}
 }
 async function apply(){if(!plan||!ready||!confirmed||!plan.can_apply||!selected.length)return;onStop();
  try{await sheet.mutateReuse('/reuse-apply',{plan_id:plan.plan_id,request:plan.request,selected_row_ids:selected});setPlan(null);setSelected([]);setMessage('已沿用選取和弦，可在下方復原這一批。');setRefresh(v=>v+1);}
  catch(e){setMessage(e instanceof Error?e.message:'沿用結果需要重新核對。');}
 }
 async function undo(id:string){if(!ready||!doc)return;onStop();try{await sheet.mutateReuse('/reuse-ledger/'+encodeURIComponent(id)+'/undo',{
   expected_version:sheet.version,structure_version:sheet.structureVersion,fingerprint:doc.source.fingerprint,audio_sha256:doc.source.audio_sha256});setMessage('已復原這批沿用，其他修改保留。');setRefresh(v=>v+1);
  }catch(e){setMessage(e instanceof Error?e.message:'復原結果需要重新核對。');}}
 return <details className="sc-reuse" open={open} onToggle={e=>setOpen(e.currentTarget.open)}><summary>沿用其他段的和弦</summary>
 {open?<><p>先比較兩段的共同核心，再把已確認的完整和弦帶到目前鎖定的「{locked?.name}」。不同結尾留在範圍外，已填好的和弦不會覆蓋。</p>
 <fieldset disabled={!ready||loading}><label>沿用來源段落<select aria-label="沿用來源段落" value={sourceId} onChange={e=>{invalidate();const s=sources.find(s=>s.id===e.target.value);setSourceId(e.target.value);if(s&&locked){setStart(s.start);setEnd(s.start+Math.min(s.end-s.start,locked.end-locked.start));setTargetStart(locked.start);}}}>{sources.map(s=><option key={s.id} value={s.id}>{s.display_label} {rootStamp(s.start)}–{rootStamp(s.end)}</option>)}</select></label>
 <div className="sc-reuse-ranges"><label>來源核心 A（秒）<input aria-label="來源核心開始秒數" type="number" step="0.001" value={Number.isFinite(start)?start:''} onChange={e=>{invalidate();setStart(e.target.value===''?NaN:Number(e.target.value));}}/></label>
 <label>來源核心 B（秒）<input aria-label="來源核心結束秒數" type="number" step="0.001" value={Number.isFinite(end)?end:''} onChange={e=>{invalidate();setEnd(e.target.value===''?NaN:Number(e.target.value));}}/></label>
 <label>目標核心 A（秒）<input aria-label="目標核心開始秒數" type="number" step="0.001" value={Number.isFinite(targetStart)?targetStart:''} onChange={e=>{invalidate();setTargetStart(e.target.value===''?NaN:Number(e.target.value));}}/></label></div>
 <p>目標核心 B：{Number.isFinite(targetEnd)?targetEnd.toFixed(3):'—'} 秒。兩段保持等長，不改變速度或調性。</p>
 <div className="sc-actions"><button disabled={!valid} onClick={()=>onPlay({start,end},sourceId)}>聽來源核心</button><button disabled={!valid||!locked} onClick={()=>locked&&onPlay({start:targetStart,end:targetEnd},locked.section_id)}>聽目標核心</button><button onClick={onStop}>停止比較</button></div>
 <label><input type="checkbox" checked={confirmed} onChange={e=>{generation.current++;setPlan(null);setSelected([]);setConfirmed(e.target.checked);}}/>我已比較兩段原曲，確認核心對齊</label>
 {!valid?<p>請選段落內至少 0.08 秒的共同範圍；目標終點不能超過鎖定段落。</p>:null}
 <button disabled={!valid} onClick={()=>void preview()}>預覽可沿用和弦</button></fieldset>
 {plan?<section aria-label="和弦沿用預覽"><ul>{plan.rows.map(row=><li key={row.id}><label><input type="checkbox" disabled={!ready||row.status!=='fillable'} checked={selected.includes(row.id)} onChange={e=>setSelected(ids=>e.target.checked?[...ids,row.id]:ids.filter(id=>id!==row.id))}/><span>{rootStamp(row.start)}–{rootStamp(row.end)} · {row.symbol??'待聽'} · {labels[row.status]}</span></label></li>)}</ul><button className="sc-primary" disabled={!ready||!confirmed||!plan.can_apply||!selected.length} onClick={()=>void apply()}>套用勾選和弦</button>{!confirmed?<p>比較原曲並確認對齊後，再重新預覽以套用。</p>:null}</section>:null}
 <p role="status" aria-label="和弦沿用狀態">{message}</p>
 <section aria-label="和弦沿用紀錄"><h3>沿用紀錄</h3>{operations.length?operations.map(op=><div key={op.id}><span>{new Date(op.created_at).toLocaleString('zh-TW')} · {op.changes.length} 個切片 · {op.status==='undone'?'已復原':'已沿用'}</span><button disabled={!ready||!op.can_undo} onClick={()=>void undo(op.id)}>復原這批沿用</button>{op.status!=='undone'&&!op.can_undo?<small>這批內容或段落已變動，請逐段核對。</small>:null}</div>):<p>尚無沿用紀錄。</p>}</section></>:null}</details>;
}
