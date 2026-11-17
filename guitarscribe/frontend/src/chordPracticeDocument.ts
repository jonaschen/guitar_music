import type {StructureSource} from './songStructureDocument';
export type TimeRange={start:number;end:number};
export type ChordPracticeSegment=TimeRange&{id:string;original_symbol:string|null;symbol:string|null;status:'pending'|'confirmed'};
export type ChordPracticeDocument={schema_version:1;source:StructureSource;segments:ChordPracticeSegment[]};
export type ChordLock=TimeRange&{section_id:string;structure_version:number;name:string};
export const sameSource=(a:StructureSource,b:StructureSource)=>['job_id','fingerprint','audio_sha256','duration','source_start'].every(k=>a[k as keyof StructureSource]===b[k as keyof StructureSource]);
export const validChordSymbol=(s:string)=>s.length<=64&&(s==='N.C.'||/^[A-G][#b]?[a-zA-Z0-9+#b()°ø-]*(?:\/[A-G][#b]?)?$/.test(s));
export function parseChordPractice(raw:string,expected?:StructureSource):ChordPracticeDocument{
 const d=JSON.parse(raw),s=d?.source;
 if(d?.schema_version!==1||!s||typeof s.job_id!=='string'||!s.job_id||!Number.isFinite(s.duration)||s.duration<=0||s.duration>7200||!Number.isFinite(s.source_start)||s.source_start<0||!['fingerprint','audio_sha256'].every(k=>/^[a-f0-9]{64}$/.test(s[k]))||expected&&!sameSource(s,expected)||!Array.isArray(d.segments)||!d.segments.length||d.segments.length>6000)throw Error('和弦稿格式或錄音來源不符。');
 const ids=new Set<string>();let end=0;
 for(const c of d.segments){
  if(!c||typeof c.id!=='string'||!/^[-a-zA-Z0-9_+]{1,160}$/.test(c.id)||ids.has(c.id)||!Number.isFinite(c.start)||!Number.isFinite(c.end)||Math.abs(c.start-end)>1e-7||c.end<=c.start||c.end>s.duration||c.original_symbol!==null&&(typeof c.original_symbol!=='string'||c.original_symbol.length>128)||c.symbol!==null&&(typeof c.symbol!=='string'||!validChordSymbol(c.symbol))||!['pending','confirmed'].includes(c.status)||(c.status==='confirmed')!==(c.symbol!==null))throw Error('和弦區段須連續、不重疊且有有效名稱。');
  ids.add(c.id);end=c.end;
 }
 if(Math.abs(end-s.duration)>1e-7)throw Error('和弦區段未完整覆蓋錄音。');return d;
}
export function applyChordRange(document:ChordPracticeDocument,lock:TimeRange,range:TimeRange,symbol:string|null):ChordPracticeDocument{
 if(!Number.isFinite(range.start+range.end+lock.start+lock.end)||lock.start<0||lock.end>document.source.duration||range.start<lock.start||range.end>lock.end||range.end-range.start<.001||symbol!==null&&!validChordSymbol(symbol))throw Error('請在鎖定段落內選範圍，和弦可填 C、Am、G7、C/E 或 N.C.。');
 const segments=document.segments.flatMap(c=>{
  if(c.end<=range.start||c.start>=range.end)return [c];
  const start=Math.max(range.start,c.start),end=Math.min(range.end,c.end);
  return [...(c.start<start?[{...c,end:start}]:[]),{...c,id:crypto.randomUUID(),start,end,symbol,status:symbol===null?'pending' as const:'confirmed' as const},...(c.end>end?[{...c,id:crypto.randomUUID(),start:end}]:[])];
 });return parseChordPractice(JSON.stringify({...document,segments}),document.source);
}
export function chordPracticeUrl(job:string,section?:{id:string;start:number;end:number},fingerprint?:string){
 const url=new URL(location.pathname,location.origin);url.searchParams.set('practice','chords');url.searchParams.set('job',job);
 if(section&&fingerprint){url.searchParams.set('structure',section.id);url.searchParams.set('structure_source',fingerprint);url.searchParams.set('section_start',String(section.start));url.searchParams.set('section_end',String(section.end));}
 return url.pathname+url.search;
}

export function restoreChordScope(current:ChordPracticeDocument,past:ChordPracticeDocument,lock:TimeRange){
 if(!sameSource(current.source,past.source))throw Error('復原稿的來源不符。');let next=current;
 for(const c of past.segments){const start=Math.max(c.start,lock.start),end=Math.min(c.end,lock.end);if(end>start)next=applyChordRange(next,lock,{start,end},c.symbol);}
 return next;
}
