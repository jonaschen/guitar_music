import {ROOT_NAMES} from './rootPracticeDocument';

// Audition register only. Saved roots remain pitch classes, not bass notes or octaves.
export const ROOT_AUDITION_MIN = 40; // Standard guitar sixth string: E2.
export const ROOT_AUDITION_MAX = 51; // Eb3, twelve consecutive semitones.
export const ROOT_AUDITION_ORDER = Array.from({length:12},(_,i)=>(ROOT_AUDITION_MIN+i)%12);
export function rootAuditionMidi(root:number){
  return ROOT_AUDITION_MIN+(root-ROOT_AUDITION_MIN%12+12)%12;
}
export function rootAuditionName(root:number){
  return `${ROOT_NAMES[root]}${Math.floor(rootAuditionMidi(root)/12)-1}`;
}
