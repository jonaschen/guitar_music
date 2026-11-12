import {rootBarAt,rootBarLength,rootBeatLength,validRootGrid,type RootGrid} from './rootPracticeGrid';
import type {RootDocument,RootSegment} from './rootPracticeDocument';

export function isMetricalDocument(d:RootDocument){
  if(d.schema_version!==2||!d.grid||!validRootGrid(d.grid,d.source.duration))return false;
  const grid=d.grid,length=rootBarLength(grid);
  return d.segments.every(s=>{
    const bar=rootBarAt(grid,(s.start+s.end)/2,d.source.duration);
    return [1,2,4].some(divisor=>grid.beats%divisor===0&&Array.from({length:divisor},(_,i)=>i).some(i=>Math.abs(s.start-Math.max(0,bar.rawStart+i*length/divisor))<1e-7&&Math.abs(s.end-Math.min(d.source.duration,bar.rawStart+(i+1)*length/divisor))<1e-7));
  });
}
function transfer(old:RootSegment[],start:number,end:number):Pick<RootSegment,'root'|'status'|'original_root'>{
  const overlaps=old.filter(s=>s.start<end-1e-8&&s.end>start+1e-8),confirmed=overlaps.filter(s=>s.status==='confirmed');
  const roots=new Set(confirmed.map(s=>s.root)),originals=new Set(overlaps.map(s=>s.original_root));
  const coverage=confirmed.reduce((total,s)=>total+Math.min(end,s.end)-Math.max(start,s.start),0);
  const root=roots.size===1&&coverage>=end-start-1e-7?[...roots][0]:null;
  return {root,status:root!==null?'confirmed':confirmed.length?'unsure':'pending',original_root:originals.size===1?[...originals][0]:null};
}
export function regridRoots(d:RootDocument,grid:RootGrid):RootDocument{
  if(!validRootGrid(grid,d.source.duration))throw Error('請先設定有效拍格。');
  const length=rootBarLength(grid),first=Math.floor(-grid.anchor/length+1e-9),last=Math.ceil((d.source.duration-grid.anchor)/length-1e-9);
  if(last-first>6000)throw Error('小節數超過6000，請縮短來源範圍。');
  const segments=Array.from({length:last-first},(_,i)=>{
    const start=Math.max(0,grid.anchor+(first+i)*length),end=Math.min(d.source.duration,grid.anchor+(first+i+1)*length);
    return {id:`grid-${i}`,start,end,...transfer(d.segments,start,end)};
  });
  return {...d,schema_version:2,grid,segments};
}
export function subdivideRootBar(d:RootDocument,time:number,divisor:1|2|4):RootDocument{
  if(!d.grid||!isMetricalDocument(d)||d.grid.beats%divisor!==0)throw Error('這個拍數無法以整拍細分。');
  const bar=rootBarAt(d.grid,time,d.source.duration),length=rootBarLength(d.grid);
  const parts=Array.from({length:divisor},(_,i)=>({start:Math.max(0,bar.rawStart+i*length/divisor),end:Math.min(d.source.duration,bar.rawStart+(i+1)*length/divisor)})).filter(s=>s.end>s.start+1e-8).map(s=>({...s,id:crypto.randomUUID(),...transfer(d.segments,s.start,s.end)}));
  const segments=[...d.segments.filter(s=>s.end<=bar.start+1e-8),...parts,...d.segments.filter(s=>s.start>=bar.end-1e-8)];
  if(segments.length>6000)throw Error('分段超過6000。');
  return {...d,segments};
}
export function rootSegmentLabel(d:RootDocument,s:RootSegment){
  if(!d.grid)return '';
  const bar=rootBarAt(d.grid,(s.start+s.end)/2,d.source.duration),beat=rootBeatLength(d.grid),length=rootBarLength(d.grid);
  const startBeat=(s.start-bar.rawStart)/beat,endBeat=(s.end-bar.rawStart)/beat;
  const clipped=(s.start===0&&bar.rawStart< -1e-8)||(s.end===d.source.duration&&bar.rawStart+length>d.source.duration+1e-8);
  const size=clipped?'首尾不完整':Math.abs(s.end-s.start-length)<1e-7?'整小節':Math.abs(s.end-s.start-length/2)<1e-7?'1/2 小節':Math.abs(s.end-s.start-length/4)<1e-7?'1/4 小節':'首尾不完整';
  return `第 ${bar.number} 小節 · ${size} · 第 ${Math.floor(startBeat+1e-7)+1}–${Math.ceil(endBeat-1e-7)} 拍`;
}
