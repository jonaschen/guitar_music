// Render diagnostic overlays with production metronome/pluck voices, not new note inference.
import {chromium} from '@playwright/test';
import {writeFile,readFile,mkdir,copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const block=process.argv.includes('--block');
const revision=process.argv[2];if(!revision)throw Error('Explicit saved revision ID required');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const api=process.env.GUITARSCRIBE_API_URL??'http://127.0.0.1:8000';
const ui=process.env.GUITARSCRIBE_UI_URL??'http://127.0.0.1:5173';
async function json(url,options){const r=await fetch(url,options);if(!r.ok)throw Error(`${r.status} ${url}`);return r.json();}
const score=await json(`${api}/revisions/${encodeURIComponent(revision)}`);
const config=JSON.parse(await readFile(path.join(root,'public/listening/ensemble-2026-10-18/config.json'),'utf8'));
assert.equal(config.revision,revision);
const start=score.beats.find(b=>b.measure===28&&b.beat===1).time,end=score.beats.find(b=>b.measure===36&&b.beat===1).time;
assert.equal(config.start,start);assert.equal(config.end,end);
const manifest=await json(`${api}/scores/playback/manifest`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(score)});
const spans=[];
for(const chord of score.chords){
 const previous=spans.at(-1);
 if(previous&&previous.symbol===chord.symbol&&Math.abs(previous.end-chord.start)<1e-9)previous.end=chord.end;
 else spans.push({symbol:chord.symbol,start:chord.start,end:chord.end});
}
const blocks=spans.filter(c=>c.end>start&&c.start<end).map(c=>{
 const event=manifest.events.find(e=>e.track==='guitar'&&e.start>=c.start-1e-9&&e.start<c.end);
 assert.ok(event,`No playable voicing for ${c.symbol}`);
 return {...event,start:c.start,end:c.end,sustain_end:c.end,pitch_offsets:event.pitches.map(()=>0),symbol:c.symbol};
});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const out=path.join(root,block?'public/listening/harmony-block-2026-10-21':'public/listening/alignment-isolation-2026-10-21');await mkdir(out,{recursive:true});
const results=[];
try{
 const page=await browser.newPage();await page.goto(`${ui}/listening/ensemble-2026-10-18/source.wav`);
 for(const mode of (block?['harmony']:['beats','guitar'])){
  const result=await page.evaluate(async({score,manifest,blocks,start,end,mode})=>{
   const {createMetronomeVoice}=await import('/src/metronomeVoice.ts');
   const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
   const rate=22050,context=new OfflineAudioContext(1,Math.round((end-start)*rate),rate);
   const data=await (await fetch('/listening/ensemble-2026-10-18/source.wav')).arrayBuffer();
   const source=context.createBufferSource(),gain=context.createGain();source.buffer=await context.decodeAudioData(data);gain.gain.value=.45;source.connect(gain).connect(context.destination);source.start(0);
   const timings=[];
   if(mode==='beats')for(const b of score.beats.filter(b=>b.time>=start&&b.time<end)){
    createMetronomeVoice(context,b.time-start,b.beat===1,.8);timings.push(b.time-start);
   }
   if(mode==='guitar'||mode==='harmony'){
    const events=(mode==='harmony'?blocks:manifest.events).filter(e=>e.track==='guitar'&&(e.sustain_end??e.end)>start&&e.start<end);
    const buffers=await preparePluckedBuffers(context,events.flatMap(e=>e.pitches));
    for(const e of events)for(let i=0;i<e.pitches.length;i++){
     const onset=e.start+(e.pitch_offsets[i]??i*.012),at=Math.max(0,onset-start),until=Math.min(end,e.sustain_end??e.end)-start,age=Math.max(0,start-onset);
     const node=createPluckedVoice(context,buffers.get(e.pitches[i]),at,until,.24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),age,e.stroke);
     if(node)timings.push(at);
    }
   }
   const buffer=await context.startRendering(),samples=Array.from(buffer.getChannelData(0));
   let peak=0,sum=0;for(const sample of samples){peak=Math.max(peak,Math.abs(sample));sum+=sample*sample;}
   return {samples,peak,rms:Math.sqrt(sum/samples.length),timings,rate};
  },{score,manifest,blocks,start,end,mode});
  assert.ok(result.peak<1&&result.rms>.01,`${mode}: clipping/silence`);
  assert.ok(result.timings.length>0&&result.timings.every(t=>t>=0&&t<end-start));
  if(mode==='beats')assert.deepEqual(result.timings,score.beats.filter(b=>b.time>=start&&b.time<end).map(b=>b.time-start));
  const wav=Buffer.alloc(44+result.samples.length*2);wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(result.rate,24);wav.writeUInt32LE(result.rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
  result.samples.forEach((v,i)=>wav.writeInt16LE(Math.round(v*32767),44+i*2));await writeFile(path.join(out,`${mode}.wav`),wav);
  results.push({mode,frames:result.samples.length,peak:result.peak,rms:result.rms,eventCount:result.timings.length,timings:result.timings});
 }
}finally{await browser.close();}
assert.deepEqual(await json(`${api}/revisions/${encodeURIComponent(revision)}`),score);
await copyFile(path.join(root,block?'scripts/harmony-block.html':'scripts/alignment-isolation.html'),path.join(out,'index.html'));
await writeFile(path.join(out,'report.json'),JSON.stringify({revision,start,end,sourceGain:.45,blockControl:block,blocks:block?blocks:undefined,sourceOffset:score.song.source_start_seconds,interpretation:'Diagnostic overlays; no correction and no accuracy claim',savedRevisionUnchanged:true,results},null,2));
console.log(JSON.stringify({out,results:results.map(({timings,...r})=>r)}));
