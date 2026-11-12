export const ROOT_NAMES=['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B'];
export type RootSource={job_id:string;fingerprint:string;duration:number;source_start:number};
export type RootSegment={id:string;start:number;end:number;original_root:number|null;root:number|null;status:'pending'|'confirmed'|'unsure'};
export type RootDocument={schema_version:1;source:RootSource;segments:RootSegment[]};
export type RootSnapshot={job_id:string;version:number;document:RootDocument;updated_at:string|null};
export function parseRootDocument(raw:string,source?:RootSource):RootDocument{
  const d=JSON.parse(raw) as RootDocument;
  const pitch=(p:unknown)=>p===null||typeof p==='number'&&Number.isInteger(p)&&p>=0&&p<12;
  if(d?.schema_version!==1||!d.source||!Number.isFinite(d.source.duration)||d.source.duration<=0||d.source.duration>7200||!Number.isFinite(d.source.source_start)||d.source.source_start<0||!d.source.job_id||!/^[a-f0-9]{64}$/.test(d.source.fingerprint)||!Array.isArray(d.segments)||!d.segments.length||d.segments.length>6000)throw Error('練習備份格式不完整。');
  if(source&&(d.source.job_id!==source.job_id||d.source.fingerprint!==source.fingerprint||d.source.duration!==source.duration||d.source.source_start!==source.source_start))throw Error('這份備份屬於不同的歌曲或來源片段。');
  const ids=new Set<string>();let cursor=0;
  for(const s of d.segments){
    if(!s||!/^[a-zA-Z0-9_-]{1,80}$/.test(s.id)||ids.has(s.id)||!Number.isFinite(s.start)||!Number.isFinite(s.end)||Math.abs(s.start-cursor)>1e-7||s.end<=s.start||!pitch(s.root)||!pitch(s.original_root)||!['pending','confirmed','unsure'].includes(s.status)||(s.status==='confirmed')!==(s.root!==null))throw Error('區段時間或根音內容無效。');
    ids.add(s.id);cursor=s.end;
  }
  if(Math.abs(cursor-d.source.duration)>1e-7)throw Error('區段範圍與原曲不符。');
  return d;
}
export function splitRootSegment(d:RootDocument,id:string,time:number):RootDocument{
  const s=d.segments.find(s=>s.id===id);
  if(!s||time-s.start<.08||s.end-time<.08||!Number.isFinite(time))throw Error('請在這段中間暫停，再從游標處分段。');
  return {...d,segments:d.segments.flatMap(s=>s.id===id?[{...s,end:time,root:null,status:'pending' as const},{...s,id:crypto.randomUUID(),start:time,root:null,status:'pending' as const}]:[s])};
}
export function mergeRootSegment(d:RootDocument,id:string):RootDocument{
  const index=d.segments.findIndex(s=>s.id===id),s=d.segments[index],next=d.segments[index+1];
  if(!s||!next)throw Error('已是最後一段。');
  return {...d,segments:d.segments.flatMap((v,i)=>i===index?[{...s,end:next.end,original_root:s.original_root===next.original_root?s.original_root:null,root:null,status:'pending' as const}]:i===index+1?[]:[v])};
}
export const rootStamp=(t:number)=>`${Math.floor(t/60)}:${(t%60).toFixed(1).padStart(4,'0')}`;
export function rootText(d:RootDocument){return ['根音行進（個人聽辨稿，非已驗證答案）','時間為分析片段內秒數；原曲起點 '+d.source.source_start+' 秒',...d.segments.map(s=>`${s.start.toFixed(3)}–${s.end.toFixed(3)}\t${s.root===null?'?':ROOT_NAMES[s.root]}\t${s.status==='confirmed'?'已採用':s.status==='unsure'?'還聽不出來':'待聽'}`)].join('\n');}
