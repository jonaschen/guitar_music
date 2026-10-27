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
