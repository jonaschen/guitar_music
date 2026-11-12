import {ROOT_NAMES} from './rootPracticeDocument';

// Audition register only. Saved roots remain pitch classes, not bass notes or octaves.
export const ROOT_AUDITION_MIN = 39; // Additional low Eb2, below the guitar's E2.
export const ROOT_AUDITION_MAX = 51; // Preserve the existing upper Eb3.
export const ROOT_AUDITION_ORDER = Array.from({length:13},(_,i)=>ROOT_AUDITION_MIN+i);
export function rootAuditionMidi(root:number){
  return 40+(root-4+12)%12; // Existing candidate/progression register stays E2–Eb3.
}
export function auditionMidiName(midi:number){return `${ROOT_NAMES[midi%12]}${Math.floor(midi/12)-1}`;}
export function rootAuditionName(root:number){
  return auditionMidiName(rootAuditionMidi(root));
}
