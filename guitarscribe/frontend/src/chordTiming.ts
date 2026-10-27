import type {SongScore} from './types';

// Use the detected beat intervals, not a constant BPM approximation.
export function beatCoordinate(score: SongScore, time: number): number {
  const beats=score.beats.map(b=>b.time);
  if(beats.length<2 || beats.some((t,i)=>!Number.isFinite(t)||(i>0&&t<=beats[i-1]))) throw new Error('目前拍點不足，請先確認拍格，再調整拍長。');
  let i=beats.findIndex(t=>t>time)-1;
  if(i===-2)i=beats.length-2;
  i=Math.max(0,i);
  return i+(time-beats[i])/(beats[i+1]-beats[i]);
}
export function shiftByBeats(score: SongScore,time:number,delta:number):number {
  const position=beatCoordinate(score,time)+delta;
  const i=Math.max(0,Math.min(score.beats.length-2,Math.floor(position)));
  return score.beats[i].time+(position-i)*(score.beats[i+1].time-score.beats[i].time);
}
export function retimeChord(score:SongScore,id:string,start:number,end:number):SongScore {
  const ordered=[...score.chords].sort((a,b)=>a.start-b.start);
  const index=ordered.findIndex(c=>c.id===id),current=ordered[index];
  if(!current)throw new Error('找不到要修改的和弦。');
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>score.song.duration_seconds||end-start<.1-1e-8)throw new Error('拍長超出歌曲範圍，或讓和弦短於 0.1 秒，請減少調整幅度。');
  const previous=ordered[index-1],next=ordered[index+1];
  const movePrevious=previous&&Math.abs(previous.end-current.start)<1e-6&&start!==current.start;
  const moveNext=next&&Math.abs(next.start-current.end)<1e-6&&end!==current.end;
  const chords=score.chords.map(c=>c.id===id?{...c,start,end,origin:'user',edited:true}:movePrevious&&c.id===previous.id?{...c,end:start,origin:'user',edited:true}:moveNext&&c.id===next.id?{...c,start:end,origin:'user',edited:true}:c);
  const sorted=[...chords].sort((a,b)=>a.start-b.start);
  if(sorted.some((c,i)=>(!score.chords.includes(c)&&c.end-c.start<.1-1e-8)||(i>0&&c.start<sorted[i-1].end-1e-8)))throw new Error('這次調整會跨過其他和弦，或讓相鄰和弦太短，請減少調整幅度。');
  return {...score,chords};
}
