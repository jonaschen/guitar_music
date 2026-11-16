export const STRUCTURE_NAMES={intro:'前奏',verse:'主歌',prechorus:'副歌前段',chorus:'副歌',bridge:'橋段',outro:'尾奏',inst:'器樂段／間奏候選',solo:'獨奏段／間奏候選',break:'停頓／過渡',start:'開頭未判定',end:'結尾未判定',unknown:'未判定',closing:'收尾段',custom:'自訂名稱'};
export type StructureLabel=keyof typeof STRUCTURE_NAMES;
export type StructureSource={job_id:string;fingerprint:string;audio_sha256:string;duration:number;source_start:number};
export type ModelSection={id:string;start:number;end:number;label:string;model_end:number|null;original_number:number|null};
export type StructureSection={id:string;start:number;end:number;label:StructureLabel;display_label:string;name_review_status:'unreviewed'|'user_corrected'|'user_confirmed'|'tentative';boundary_review_status:'unreviewed'|'user_confirmed';model_sections:ModelSection[];note:string};
export type StructureDocument={schema_version:1;source:StructureSource;candidate_sha256:string|null;sections:StructureSection[]};
export type StructureSnapshot={job_id:string;document:StructureDocument|null;version:number;updated_at:string|null;current_source:StructureSource|null;source_matches:boolean;source_error:string|null};
const finite=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n);
const same=(a:StructureSource,b:StructureSource)=>Object.keys(a).every(k=>a[k as keyof StructureSource]===b[k as keyof StructureSource]);
function fields(v:any,keys:string[]){if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).some(k=>!keys.includes(k)))throw Error('結構備份欄位不符。');}
export function parseStructure(text:string,source?:StructureSource):StructureDocument{
 const d=JSON.parse(text);fields(d,['schema_version','source','candidate_sha256','sections']);
 fields(d.source,['job_id','fingerprint','audio_sha256','duration','source_start']);const s=d.source;
 if(d.schema_version!==1||typeof s.job_id!=='string'||!s.job_id||s.job_id.length>100||!/^([a-f0-9]{64})$/.test(s.fingerprint)||!/^([a-f0-9]{64})$/.test(s.audio_sha256)||!finite(s.duration)||s.duration<=0||s.duration>7200||!finite(s.source_start)||s.source_start<0||source&&!same(s,source))throw Error('結構備份與目前錄音來源不符。');
 if(d.candidate_sha256!==null&&!/^[a-f0-9]{64}$/.test(d.candidate_sha256))throw Error('初稿版本不符。');
 if(!Array.isArray(d.sections)||!d.sections.length||d.sections.length>2000)throw Error('結構段落數量無效。');
 let cursor=0,references=0;const ids=new Set();const originals=new Map<string,string>();
 for(const x of d.sections){
  fields(x,['id','start','end','label','display_label','name_review_status','boundary_review_status','model_sections','note']);
  if(typeof x.id!=='string'||!/^[-a-zA-Z0-9_+]{1,160}$/.test(x.id)||ids.has(x.id)||!finite(x.start)||!finite(x.end)||Math.abs(x.start-cursor)>1e-7||x.end<=x.start||x.end>s.duration||!Object.prototype.hasOwnProperty.call(STRUCTURE_NAMES,x.label)||typeof x.display_label!=='string'||!x.display_label.trim()||x.display_label.length>120||typeof x.note!=='string'||x.note.length>2000||!['unreviewed','user_corrected','user_confirmed','tentative'].includes(x.name_review_status)||!['unreviewed','user_confirmed'].includes(x.boundary_review_status)||!Array.isArray(x.model_sections))throw Error('段落須連續、不重疊且有有效名稱。');
  references+=x.model_sections.length;const modelIds=new Set();
  if(x.model_sections.length>2000||references>20000||x.model_sections.length&&d.candidate_sha256===null)throw Error('原模型記錄數量或版本無效。');
  for(const m of x.model_sections){
   fields(m,['id','start','end','label','model_end','original_number']);
   if(typeof m.id!=='string'||!/^[-a-zA-Z0-9_+]{1,160}$/.test(m.id)||modelIds.has(m.id)||!Object.prototype.hasOwnProperty.call(STRUCTURE_NAMES,m.label)||!finite(m.start)||!finite(m.end)||m.start<0||m.end<=m.start||m.end>s.duration+.05||m.model_end!==null&&(!finite(m.model_end)||m.model_end<=m.start||m.model_end>s.duration+.05)||m.original_number!==null&&(!Number.isInteger(m.original_number)||m.original_number<1))throw Error('原模型紀錄無效。');
   const encoded=JSON.stringify([m.id,m.start,m.end,m.label,m.model_end,m.original_number]);if(originals.has(m.id)&&originals.get(m.id)!==encoded)throw Error('原模型記錄互相衝突。');originals.set(m.id,encoded);modelIds.add(m.id);
  }
  ids.add(x.id);cursor=x.end;
 }
 if(Math.abs(cursor-s.duration)>1e-7)throw Error('結構必須覆蓋整首錄音。');return d;
}
const copy=(d:StructureDocument)=>structuredClone(d);
function index(d:StructureDocument,id:string){const i=d.sections.findIndex(s=>s.id===id);if(i<0)throw Error('段落已變動，請重新選取。');return i;}
const unique=()=>`section_${crypto.randomUUID().replace(/-/g,'')}`;
const checked=(d:StructureDocument)=>parseStructure(JSON.stringify(d));
export function renameSection(doc:StructureDocument,id:string,label:StructureLabel,display=STRUCTURE_NAMES[label]){const d=copy(doc),s=d.sections[index(d,id)];s.label=label;s.display_label=display.trim();s.name_review_status='user_corrected';return checked(d);}
export function moveBoundary(doc:StructureDocument,id:string,time:number){const d=copy(doc),i=index(d,id);if(i===0||!finite(time)||time<=d.sections[i-1].start||time>=d.sections[i].end)throw Error('交界須介於左右兩段之內。');d.sections[i-1].end=time;d.sections[i].start=time;d.sections[i-1].boundary_review_status=d.sections[i].boundary_review_status='unreviewed';return checked(d);}
export function splitSection(doc:StructureDocument,id:string,time:number){const d=copy(doc),i=index(d,id),s=d.sections[i];if(!finite(time)||time<=s.start||time>=s.end)throw Error('分開位置須在這段之內。');const left={...s,id:unique(),end:time,name_review_status:'unreviewed' as const,boundary_review_status:'unreviewed' as const},right={...s,id:unique(),start:time,name_review_status:'unreviewed' as const,boundary_review_status:'unreviewed' as const};d.sections.splice(i,1,left,right);return checked(d);}
export function mergeSection(doc:StructureDocument,id:string){const d=copy(doc),i=index(d,id),a=d.sections[i],b=d.sections[i+1];if(!b)throw Error('最後一段沒有下一段可合併。');const models=[...new Map([...a.model_sections,...b.model_sections].map(s=>[s.id,s])).values()];d.sections.splice(i,2,{...a,id:unique(),end:b.end,name_review_status:'unreviewed',boundary_review_status:'unreviewed',model_sections:models,note:[a.note,b.note].filter(Boolean).join('\n')});return checked(d);}
export function confirmSection(doc:StructureDocument,id:string,kind:'name'|'boundary'){const d=copy(doc),s=d.sections[index(d,id)];if(kind==='name')s.name_review_status='user_confirmed';else s.boundary_review_status='user_confirmed';return checked(d);}
export function blankStructure(source:StructureSource):StructureDocument{return {schema_version:1,source,candidate_sha256:null,sections:[{id:unique(),start:0,end:source.duration,label:'unknown',display_label:'未判定',name_review_status:'unreviewed',boundary_review_status:'unreviewed',model_sections:[],note:''}]};}
export function structurePracticeUrl(doc:StructureDocument,s:StructureSection){const url=new URL(window.location.href);url.searchParams.set('practice','roots');url.searchParams.set('visual','1');url.searchParams.set('job',doc.source.job_id);url.searchParams.set('structure',s.id);url.searchParams.set('structure_source',doc.source.fingerprint);url.searchParams.set('section_start',String(s.start));url.searchParams.set('section_end',String(s.end));url.searchParams.set('section_name',s.display_label);return url.pathname+url.search;}
