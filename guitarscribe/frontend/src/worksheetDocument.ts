export type WorksheetAnchor={time:number;end:number|null;source_start_seconds:number;duration_seconds:number;kind:'seconds'|'metered'|'local';grid_id:string|null};
export type WorksheetLine={id:string;lyric:string;notation:string;anchor:WorksheetAnchor|null;start:number|null;end:number|null};
export type WorksheetDocument={source:string;lines:WorksheetLine[]};
export const emptyWorksheet:WorksheetDocument={source:'',lines:[]};
export function encodeDocument(value:unknown):string{
  const d=value as WorksheetDocument;
  if(!d||typeof d.source!=='string'||d.source.length>500||!Array.isArray(d.lines)||d.lines.length>400)throw Error('工作頁格式不完整');
  const ids=new Set<string>();
  const lines=d.lines.map(row=>{
    if(!row||typeof row.id!=='string'||!/^[-A-Za-z0-9_]{1,80}$/.test(row.id)||ids.has(row.id)||typeof row.lyric!=='string'||typeof row.notation!=='string'||row.lyric.length>2000||row.notation.length>2000)throw Error('工作頁行資料不完整');
    ids.add(row.id);
    const start=row.start??null,end=row.end??null;
    if([start,end].some(t=>t!==null&&(!Number.isFinite(t)||t<0))||start!==null&&end!==null&&end<=start)throw Error('參考時間格式不完整');
    const a=row.anchor??null;
    let anchor:WorksheetAnchor|null=null;
    if(a!==null){
      if(!['seconds','metered','local'].includes(a.kind)||[a.time,a.source_start_seconds,a.duration_seconds].some(t=>typeof t!=='number'||!Number.isFinite(t))||a.time<0||a.source_start_seconds<0||a.duration_seconds<=0||a.time>=a.duration_seconds||a.end!==null&&(typeof a.end!=='number'||!Number.isFinite(a.end)||a.end<=a.time||a.end>a.duration_seconds)||a.grid_id!==null&&(typeof a.grid_id!=='string'||a.grid_id.length>80)||a.kind!=='seconds'&&!a.grid_id)throw Error('定位範圍不完整');
      anchor={time:a.time,end:a.end,source_start_seconds:a.source_start_seconds,duration_seconds:a.duration_seconds,kind:a.kind,grid_id:a.grid_id};
    }
    return {id:row.id,lyric:row.lyric,notation:row.notation,anchor,start,end};
  });
  if(lines.reduce((n,row)=>n+row.lyric.length+row.notation.length,d.source.length)>160000)throw Error('工作頁內容過長');
  return JSON.stringify({source:d.source,lines});
}
export const newLine=(lyric='',start:number|null=null,end:number|null=null):WorksheetLine=>({id:crypto.randomUUID(),lyric,notation:'',anchor:null,start,end});
export function pastedDocument(text:string,lrc=false):WorksheetDocument{
  const source=lrc?'使用者LRC；參考時間尚未核對':'使用者貼上；未對時';
  let lines:WorksheetLine[]=[];
  for(const raw of text.replace(/^\uFEFF/,'').split(/\r?\n/)){
    if(!lrc){lines.push(newLine(raw));continue;}
    const tags=[...raw.matchAll(/\[(\d+):(\d+(?:\.\d+)?)\]/g)];
    const lyric=raw.replace(/\[(\d+):(\d+(?:\.\d+)?)\]/g,'');
    if(tags.length)for(const tag of tags)lines.push(newLine(lyric,Number(tag[1])*60+Number(tag[2])));
    else if(!/^\[(ar|al|ti|by|offset):/i.test(raw))lines.push(newLine(raw));
  }
  if(lrc){const timed=lines.filter(r=>r.start!==null).sort((a,b)=>a.start!-b.start!);if(timed.length===lines.length)lines=timed;}
  const doc={source,lines};encodeDocument(doc);return doc;
}
