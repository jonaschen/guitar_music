export type WorksheetLine={id:string;lyric:string;notation:string;start:number|null;end:number|null};
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
    return {id:row.id,lyric:row.lyric,notation:row.notation,start,end};
  });
  if(lines.reduce((n,row)=>n+row.lyric.length+row.notation.length,d.source.length)>160000)throw Error('工作頁內容過長');
  return JSON.stringify({source:d.source,lines});
}
export const newLine=(lyric='',start:number|null=null,end:number|null=null):WorksheetLine=>({id:crypto.randomUUID(),lyric,notation:'',start,end});
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
