import {rootAuditionMidi} from './rootPracticePitch';

// Steady harmonics keep the reference audible throughout comparison, without
// periodic pluck attacks or a decaying four-second sample.
export function createRootTone(context:BaseAudioContext,root:number,start:number,destination:AudioNode,end?:number){
  const oscillator=context.createOscillator(),gain=context.createGain();
  const real=new Float32Array(7),imag=new Float32Array(7);
  for(let harmonic=1;harmonic<imag.length;harmonic++)imag[harmonic]=1/harmonic**1.5;
  oscillator.setPeriodicWave(context.createPeriodicWave(real,imag));
  oscillator.frequency.setValueAtTime(440*2**((rootAuditionMidi(root)-69)/12),start);
  const fade=Math.min(.015,end===undefined?.015:(end-start)/2);
  gain.gain.setValueAtTime(0,start);
  gain.gain.linearRampToValueAtTime(.3,start+fade);
  if(end!==undefined){
    gain.gain.setValueAtTime(.3,end-fade);
    gain.gain.linearRampToValueAtTime(0,end);
  }
  oscillator.connect(gain).connect(destination);
  oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
  oscillator.start(start);
  if(end!==undefined)oscillator.stop(end+.001);
  return oscillator;
}
