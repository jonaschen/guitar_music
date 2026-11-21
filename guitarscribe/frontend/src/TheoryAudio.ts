/** Explicit reference sounds, never mixed into original-audio practice. */
export const STOP_REFERENCE='guitarscribe:stop-reference';
export function stopReference(){window.dispatchEvent(new Event(STOP_REFERENCE));}
export class TheoryAudio {
 private context:AudioContext|null=null;
 private sources=new Set<OscillatorNode>();
 private gains=new Set<GainNode>();
 private generation=0;
 stop(){this.generation++;for(const source of this.sources){try{source.stop();}catch{/* Already ended. */}source.disconnect();}this.sources.clear();for(const gain of this.gains)gain.disconnect();this.gains.clear();if(this.context&&this.context.state!=='closed')void this.context.suspend().catch(()=>{});}
 async play(midis:number[],volume:number,sequential=false){
  this.stop();if(!midis.length||midis.some(m=>!Number.isFinite(m)||m<24||m>96))return;
  const ticket=this.generation,context=this.context??new AudioContext();this.context=context;await context.resume();
  if(ticket!==this.generation)return;
  if(document.hidden){this.stop();return;}
  const start=context.currentTime+.03;
  midis.forEach((midi,index)=>{
   const osc=context.createOscillator(),gain=context.createGain(),at=start+(sequential?index*.4:0),duration=sequential ? .36 : .9;
   osc.type='sine';osc.frequency.value=440*2**((midi-69)/12);
   gain.gain.setValueAtTime(0,at);gain.gain.linearRampToValueAtTime(Math.max(0,Math.min(.3,volume))/(sequential?1:midis.length),at+.02);
   gain.gain.setValueAtTime(Math.max(0,Math.min(.3,volume))/(sequential?1:midis.length),at+duration-.08);gain.gain.linearRampToValueAtTime(0,at+duration);
   osc.connect(gain);gain.connect(context.destination);this.sources.add(osc);this.gains.add(gain);
   osc.onended=()=>{this.sources.delete(osc);this.gains.delete(gain);osc.disconnect();gain.disconnect();if(ticket===this.generation&&!this.sources.size)void context.suspend().catch(()=>{});};
   osc.start(at);osc.stop(at+duration+.01);
  });
 }
 dispose(){this.stop();void this.context?.close().catch(()=>{});this.context=null;}
}
