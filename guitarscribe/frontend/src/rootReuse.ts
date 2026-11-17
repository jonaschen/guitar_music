import {ROOT_NAMES,rootStamp,type RootDocument,type RootSegment} from './rootPracticeDocument';
import {rootBarLength,type RootGrid} from './rootPracticeGrid';
import type {StructureSection} from './songStructureDocument';
export type Range={start:number;end:number};
export type ReuseRequest={expected_version:number;fingerprint:string;audio_sha256:string;source_range:Range;target_range:Range;alignment_confirmed:boolean;source_label:string;target_label:string};
export type ReuseRow={target_id:string;start:number;end:number;source_ids:string[];root:number|null;status:'fillable'|'already_same'|'target_protected'|'source_unknown'|'source_changes'};
export type ReusePlan={job_id:string;version:number;plan_id:string;document_digest:string;request:ReuseRequest;grid:RootGrid;beat_count:number;rows:ReuseRow[];counts:Record<string,number>;can_apply:boolean};
export type ReuseOperation={id:string;status:'applied'|'undone';applied_version:number;request:ReuseRequest;source_ids:string[];target_ids:string[];mapping_matches:boolean;target_matches:boolean;can_undo:boolean;fully_equivalent:boolean;changes:{target_id:string;before:RootSegment;after:RootSegment}[]};
export function excluded(section:Range,core:Range){return [{start:section.start,end:core.start},{start:core.end,end:section.end}].filter(x=>x.end-x.start>1e-7);}
export function comparisonCore(source:Range,target:Range,grid:RootGrid){
 const bar=rootBarLength(grid),start=(r:Range)=>grid.anchor+Math.ceil((r.start-grid.anchor)/bar-1e-8)*bar;
 const a=start(source),b=start(target),bars=Math.floor(Math.min(source.end-a,target.end-b)/bar+1e-8);
 if(bars<1)return null;const s={start:a,end:a+bars*bar},t={start:b,end:b+bars*bar};
 return {source:s,target:t,bars,sourceExcluded:excluded(source,s),targetExcluded:excluded(target,t)};
}
export function barStarts(range:Range,grid:RootGrid){const length=rootBarLength(grid),start=grid.anchor+Math.ceil((range.start-grid.anchor)/length-1e-8)*length;return Array.from({length:Math.max(0,Math.floor((range.end-start)/length+1e-8))},(_,i)=>start+i*length);}
const stamp=(r:Range)=>`${rootStamp(r.start)}–${rootStamp(r.end)}`;
export function structureSheet(sections:StructureSection[],document:RootDocument,operations:ReuseOperation[],deferred:Range[]=[]){
 const valid=operations.filter(o=>o.status==='applied'&&o.mapping_matches&&o.target_matches);
 const reused=new Set(valid.flatMap(o=>o.target_ids));
 const expanded_order=sections.map(s=>({id:s.id,name:s.display_label,start:s.start,end:s.end,
  roots:document.segments.filter(r=>r.start<s.end&&r.end>s.start).map(r=>({...r,start:Math.max(r.start,s.start),end:Math.min(r.end,s.end),original_start:r.start,original_end:r.end})),
  references:operations.filter(o=>o.status==='applied'&&o.request.target_range.start<s.end&&o.request.target_range.end>s.start).map(o=>({operation_id:o.id,source:o.request.source_range,target:o.request.target_range,state:o.mapping_matches&&o.target_matches?'已確認沿用':'待重新比較',exceptions:excluded(s,{start:Math.max(s.start,o.request.target_range.start),end:Math.min(s.end,o.request.target_range.end)}),complete:o.fully_equivalent&&o.mapping_matches&&o.target_matches}))}));
 const notation:Array<{name:string;occurrence_ids:string[];repeat:number}>=[];
 const equal=(a:Range,b:Range)=>Math.abs(a.start-b.start)<1e-7&&Math.abs(a.end-b.end)<1e-7;
 for(let i=0;i<expanded_order.length;i++){
  const current=expanded_order[i],previous=expanded_order[i-1],last=notation.at(-1);
  const repeated=previous&&last&&current.references.some(r=>r.complete&&equal(r.target,current)&&last.occurrence_ids.some(id=>{const original=expanded_order.find(s=>s.id===id)!;return equal(r.source,original);}));
  if(repeated){last.occurrence_ids.push(current.id);last.repeat++;}else notation.push({name:current.name,occurrence_ids:[current.id],repeat:1});
 }
 const metrics={deferred:document.segments.filter(r=>r.status!=='confirmed'&&deferred.some(s=>r.start>=s.start&&r.end<=s.end)).length,total:document.segments.length,confirmed:document.segments.filter(s=>s.status==='confirmed').length,pending:document.segments.filter(s=>s.status==='pending').length,unsure:document.segments.filter(s=>s.status==='unsure').length,reused:document.segments.filter(s=>s.status==='confirmed'&&reused.has(s.id)).length};
 const definitions=expanded_order.map(s=>({id:s.id,name:s.name,roots:s.roots}));
 const lines=expanded_order.map((s,i)=>`${i+1}. ${s.name} [${stamp(s)}]\n   ${s.roots.map(r=>`${stamp(r)} ${r.status==='confirmed'&&r.root!==null?ROOT_NAMES[r.root]:'?'}${r.status==='unsure'?'（再聽）':''}`).join(' | ')}${s.references.map(r=>`\n   ${r.state}：${stamp(r.target)} 參照 ${stamp(r.source)}${r.complete?'':'；部分沿用或需核對，其他位置保留原判斷'}`).join('')}`);
 return {schema_version:1,source:document.source,definitions,expanded_order,notation,metrics,practice_focus:{deferred_ranges:deferred,scope:'this_browser'},text:`歌曲結構與根音行進（依原錄音順序）\n${notation.map(n=>n.name+(n.repeat>1?` ×${n.repeat}`:``)).join(` → `)}\n已採用 ${metrics.confirmed}／${metrics.total}，其中有效沿用 ${metrics.reused}；待聽 ${metrics.pending}、再聽 ${metrics.unsure}（其中暫不練 ${metrics.deferred}）\n\n${lines.join('\n\n')}`};
}
