import type {SongScore} from './types';
export type ChordEditScope = {start:number;end:number;bar:number};
type Chord=SongScore['chords'][number];

// A displayed bar cell can be just part of a longer source event. Split only
// when applying an edit, keeping both outside portions and the source immutable.
export function editChordSlice(chords:Chord[],id:string,scope:ChordEditScope|null,updates:Partial<Chord>):Chord[] {
  return chords.flatMap(chord=>{
    if(chord.id!==id)return [chord];
    if(!scope)return [{...chord,...updates}];
    const start=Math.max(chord.start,scope.start),end=Math.min(chord.end,scope.end);
    if(end<=start)throw new Error('這段和弦的位置已改變，請重新點選要修改的小節。');
    return [
      ...(chord.start<start?[{...chord,id:crypto.randomUUID(),end:start}]:[]),
      {...chord,...updates,start,end},
      ...(chord.end>end?[{...chord,id:crypto.randomUUID(),start:end}]:[]),
    ];
  });
}

// Remove only the displayed intersection. A preceding contiguous chord in
// this bar fills the removed span; otherwise retain an explicit gap.
export function removeChordSlice(chords:Chord[],id:string,scope:ChordEditScope):Chord[] {
  const selected=chords.find(c=>c.id===id);
  if(!selected)throw new Error('找不到要刪除的和弦，請重新點選。');
  const start=Math.max(selected.start,scope.start),end=Math.min(selected.end,scope.end);
  if(end<=start)throw new Error('和弦位置已改變，請重新點選小節。');
  const previous=chords.find(c=>c.id!==id && c.end>scope.start && Math.abs(c.end-start)<1e-8 && c.start<start);
  return chords.flatMap(c=>{
    if(c.id===id)return [
      ...(c.start<start?[{...c,end:start,origin:"user",edited:true}]:[]),
      ...(c.end>end?[{...c,id:c.start<start?crypto.randomUUID():c.id,start:end,origin:"user",edited:true}]:[]),
    ];
    return [previous?.id===c.id?{...c,end,origin:'user',edited:true}:c];
  });
}
