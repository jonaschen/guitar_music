import {createRootTone} from './rootPracticeTone';
export type RootAudioMode='source'|'mix'|'root';
export type RootAudioOptions={url:string;start:number;end:number;from?:number;loop:boolean;mode:RootAudioMode;notes:Array<{start:number;end:number;root:number}>};
export function rootClock(elapsed:number,start:number,end:number,from:number,loop:boolean){
  const position=from+Math.max(0,elapsed);
  return loop?start+((position-start)%(end-start)):Math.min(end,position);
}
export class RootPracticeAudio{
  private context:AudioContext|null=null;
  private buffer:AudioBuffer|null=null;
  private bufferUrl='';
  private generation=0;
  private nodes=new Set<AudioScheduledSourceNode>();
  private timer:ReturnType<typeof setInterval>|null=null;
  private abort:AbortController|null=null;
  private sourceGain:GainNode|null=null;
  private rootGain:GainNode|null=null;
  private sourceLevel=.75;private rootLevel=.5;
  private active:{options:RootAudioOptions;clock:number;from:number}|null=null;
  private position=0;
  constructor(private update:(position:number,state:'idle'|'preparing'|'playing',error?:string)=>void){}
  read(){const a=this.active;return a&&this.context?rootClock(this.context.currentTime-a.clock,a.options.start,a.options.end,a.from,a.options.loop):this.position;}
  volume(source:number,root:number){this.sourceLevel=source;this.rootLevel=root;if(this.context){this.sourceGain?.gain.setTargetAtTime(source,this.context.currentTime,.01);this.rootGain?.gain.setTargetAtTime(root,this.context.currentTime,.01);}}
  stop(){
    this.position=this.read();this.generation++;this.active=null;this.abort?.abort();this.abort=null;
    if(this.timer!==null)clearInterval(this.timer);this.timer=null;
    for(const node of this.nodes){try{node.stop();}catch{/* Ended already. */}node.disconnect();}this.nodes.clear();
    this.sourceGain?.disconnect();this.rootGain?.disconnect();this.sourceGain=null;this.rootGain=null;
    this.update(this.position,'idle');return this.position;
  }
  async play(options:RootAudioOptions){
    this.stop();const ticket=this.generation;
    const valid=Number.isFinite(options.start+options.end)&&options.start>=0&&options.end>options.start;
    if(!valid){this.update(this.position,'idle','這段時間無法播放。');return;}
    this.position=Math.max(options.start,Math.min(options.from??options.start,options.end-.001));
    this.update(this.position,'preparing');
    try{
      const context=this.context??new AudioContext();this.context=context;await context.resume();
      if(ticket!==this.generation)return;
      if(options.mode!=='root'&&(!this.buffer||this.bufferUrl!==options.url)){
        this.abort=new AbortController();const response=await fetch(options.url,{signal:this.abort.signal});
        if(!response.ok)throw Error('原曲目前無法播放，可先選「根音」試音。');
        const buffer=await context.decodeAudioData(await response.arrayBuffer());
        if(ticket!==this.generation)return;this.buffer=buffer;this.bufferUrl=options.url;
      }
      if(options.mode!=='root'&&this.buffer!.duration+.08<options.end)throw Error('音訊長度與練習不符，請重新載入歌曲。');
      if(ticket!==this.generation)return;
      this.sourceGain=context.createGain();this.rootGain=context.createGain();this.sourceGain.connect(context.destination);this.rootGain.connect(context.destination);this.volume(this.sourceLevel,this.rootLevel);
      const clock=context.currentTime+.04,from=this.position;
      this.active={options,clock,from};
      if(options.mode!=='root'){
        const node=context.createBufferSource();node.buffer=this.buffer;node.connect(this.sourceGain);node.loop=options.loop;node.loopStart=options.start;node.loopEnd=options.end;
        this.nodes.add(node);node.onended=()=>{this.nodes.delete(node);node.disconnect();};
        if(options.loop)node.start(clock,from);else node.start(clock,from,options.end-from);
      }
      const notes=options.mode==='source'?[]:options.notes.map(n=>({time:Math.max(n.start,options.start),end:Math.min(n.end,options.end),root:n.root})).filter(n=>n.end>n.time);
      const hold=options.loop&&notes.length===1&&notes[0].time===options.start&&notes[0].end===options.end;
      const tone=(root:number,start:number,end?:number)=>{
        const node=createRootTone(context,root,start,this.rootGain!,end);
        this.nodes.add(node);node.addEventListener('ended',()=>this.nodes.delete(node));
      };
      if(hold)tone(notes[0].root,clock);
      const attacks=hold?[]:notes;
      const scheduled=new Set<string>();const length=options.end-options.start;
      const tick=()=>{
        if(ticket!==this.generation)return;
        const now=context.currentTime,absolute=from+Math.max(0,now-clock);
        if(!options.loop&&absolute>=options.end){this.position=options.end;this.stop();return;}
        const cycle=Math.floor((absolute-options.start)/length);
        for(let c=Math.max(0,cycle);c<=cycle+1;c++){
          if(!options.loop&&c>0)break;
          for(let i=0;i<attacks.length;i++){
            const a=attacks[i],at=clock+(a.time-options.start)+c*length-(from-options.start),end=at+a.end-a.time,key=`${c}:${i}`;
            if(at>now+.18||end<=now||scheduled.has(key))continue;
            scheduled.add(key);const onset=Math.max(at,now);
            // Sustained roots share the source clock and stop at decision boundaries.
            tone(a.root,onset,end);
          }
        }
        // Keep memory bounded during an indefinitely repeated practice loop.
        if(cycle>1)for(const key of scheduled)if(Number(key.split(':')[0])<cycle-1)scheduled.delete(key);
        this.position=this.read();this.update(this.position,'playing');
      };
      tick();this.timer=setInterval(tick,40);
    }catch(error){if(ticket!==this.generation)return;this.stop();this.update(this.position,'idle',error instanceof Error?error.message:'播放準備失敗，請重試。');}
  }
  dispose(){this.stop();void this.context?.close();this.context=null;this.buffer=null;}
}
