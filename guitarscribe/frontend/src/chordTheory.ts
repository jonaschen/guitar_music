/** Dictionary definitions only. These are not detected notes from the recording. */
export type TheoryTone={name:string;pitchClass:number;midi:number;degree:string};
export type TheoryChord={symbol:string;root:string;bass:string|null;tones:TheoryTone[]};
const letters='CDEFGAB',natural=[0,2,4,5,7,9,11];
const mod=(x:number)=>((x%12)+12)%12;
export function pitchClass(note:string){const m=/^([A-G])([#b]?)$/.exec(note);return m?mod(natural[letters.indexOf(m[1])]+(m[2]==='#'?1:m[2]==='b'?-1:0)):null;}
function spelled(root:string,degree:number,semitones:number){
 const letter=(letters.indexOf(root[0])+degree-1)%7,target=mod(pitchClass(root)!+semitones);
 let difference=mod(target-natural[letter]);if(difference>6)difference-=12;
 return letters[letter]+(difference>0?'#'.repeat(difference):'b'.repeat(-difference));
}
type Formula=[number,number,string][];
const third:Formula=[[1,0,'1'],[3,4,'3'],[5,7,'5']],minor:Formula=[[1,0,'1'],[3,3,'♭3'],[5,7,'5']];
const formulas:Record<string,Formula>={
 '':third,maj:third,M:third,m:minor,min:minor,
 sus2:[[1,0,'1'],[2,2,'2'],[5,7,'5']],sus4:[[1,0,'1'],[4,5,'4'],[5,7,'5']],
 dim:[[1,0,'1'],[3,3,'♭3'],[5,6,'♭5']],aug:[[1,0,'1'],[3,4,'3'],[5,8,'♯5']],
 '5':[[1,0,'1'],[5,7,'5']],
 '7':[...third,[7,10,'♭7']],maj7:[...third,[7,11,'7']],M7:[...third,[7,11,'7']],m7:[...minor,[7,10,'♭7']],
 m7b5:[[1,0,'1'],[3,3,'♭3'],[5,6,'♭5'],[7,10,'♭7']],dim7:[[1,0,'1'],[3,3,'♭3'],[5,6,'♭5'],[7,9,'♭♭7']],
 '6':[...third,[6,9,'6']],m6:[...minor,[6,9,'6']],add9:[...third,[9,14,'9']],
};
export const theoryQualities=['','m','sus2','sus4','5','dim','aug','7','maj7','m7','m7b5','dim7','6','m6','add9'];
export function chordTones(symbol:string):TheoryChord|null{
 const m=/^([A-G][#b]?)([^/]*)(?:\/([A-G][#b]?))?$/.exec(symbol.trim());if(!m||!formulas[m[2]])return null;
 const root=m[1],pc=pitchClass(root)!;
 return {symbol:symbol.trim(),root,bass:m[3]??null,tones:formulas[m[2]].map(([degree,semitones,label])=>({
  name:spelled(root,degree,semitones),pitchClass:mod(pc+semitones),midi:60+pc+semitones,degree:label}))};
}
export function compareChordTones(a:string,b:string){
 const first=chordTones(a),second=chordTones(b);if(!first||!second)return null;
 const pcsA=new Set(first.tones.map(t=>t.pitchClass)),pcsB=new Set(second.tones.map(t=>t.pitchClass));
 const onlyA=first.tones.filter(t=>!pcsB.has(t.pitchClass)),onlyB=second.tones.filter(t=>!pcsA.has(t.pitchClass));
 return {a:first,b:second,onlyA,onlyB,samePitchClasses:onlyA.length===0&&onlyB.length===0};
}
export function relativeKey(tonic:string,mode:string){
 if(pitchClass(tonic)===null)return null;
 return mode==='major'?{tonic:spelled(tonic,6,9),mode:'minor'}:mode==='minor'?{tonic:spelled(tonic,3,3),mode:'major'}:null;
}
