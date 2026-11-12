/** Manual metronome beats: BPM is clicks per minute, not an inferred time signature. */
export type RootGrid={bpm:number;beats:number;anchor:number};
export type RootBar={index:number;number:number;start:number;end:number;rawStart:number;partial:boolean};
export function validRootGrid(grid:RootGrid,duration:number){
  return !!grid&&Number.isFinite(grid.bpm)&&grid.bpm>=20&&grid.bpm<=300&&Number.isInteger(grid.beats)&&grid.beats>=1&&grid.beats<=12&&Number.isFinite(grid.anchor)&&grid.anchor>=0&&grid.anchor<=duration;
}
export const rootBeatLength=(grid:RootGrid)=>60/grid.bpm;
export const rootBarLength=(grid:RootGrid)=>rootBeatLength(grid)*grid.beats;
export function rootBarAt(grid:RootGrid,time:number,duration:number):RootBar{
  const length=rootBarLength(grid),index=Math.floor((Math.min(Math.max(0,time),Math.max(0,duration-1e-8))-grid.anchor)/length+1e-9);
  const rawStart=grid.anchor+index*length,rawEnd=grid.anchor+(index+1)*length;
  return {index,number:index-Math.floor(-grid.anchor/length+1e-9)+1,rawStart,start:Math.max(0,rawStart),end:Math.min(duration,rawEnd),partial:rawStart< -1e-8||rawEnd>duration+1e-8};
}
export function rootNearbyBars(grid:RootGrid,time:number,duration:number){
  const length=rootBarLength(grid),at=rootBarAt(grid,time,duration);
  const first=Math.max(Math.floor(-grid.anchor/length+1e-9),at.index-2),last=Math.ceil((duration-grid.anchor)/length-1e-9)-1;
  return Array.from({length:Math.max(0,Math.min(5,last-first+1))},(_,i)=>rootBarAt(grid,Math.max(0,grid.anchor+(first+i)*length)+1e-7,duration));
}
export function rootGridBeats(grid:RootGrid,start:number,end:number){
  const beat=rootBeatLength(grid),first=Math.ceil((start-grid.anchor)/beat-1e-9),last=Math.ceil((end-grid.anchor)/beat-1e-9);
  return Array.from({length:Math.max(0,last-first)},(_,i)=>{const index=first+i;return {time:grid.anchor+index*beat,strong:((index%grid.beats)+grid.beats)%grid.beats===0};});
}
