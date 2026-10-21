// Render diagnostic overlays with production metronome/pluck voices, not new note inference.
import {chromium} from '@playwright/test';
import {writeFile,readFile,mkdir,copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const direction=process.argv.includes('--boundary-probe');
const transfer=process.argv.includes('--strum-transfer');
assert.ok(!(direction&&transfer),'Choose one probe mode');
const block=process.argv.includes('--block')||direction;
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
const out=path.join(root,transfer?'public/listening/strum-transfer-2026-10-22':direction?'public/listening/harmony-boundaries-2026-10-21':block?'public/listening/harmony-block-2026-10-21':'public/listening/alignment-isolation-2026-10-21');await mkdir(out,{recursive:true});
// Local boundary probe: only C->G and G->Am move, including the preceding chord's end.
// Render the entire passage before cropping, retaining preceding string decay at the crop boundary.
const targets=direction||transfer?blocks.filter(e=>e.start-start>7&&e.start-start<10):[];
if(direction||transfer)assert.deepEqual(targets.map(e=>e.symbol),['G','Am']);
const variants=transfer?[{mode:'A',shift:0},{mode:'B',shift:.15}]:direction?[{mode:'A',shift:0},{mode:'B',shift:.15},{mode:'C',shift:-.15}]:
 (block?['harmony']:['beats','guitar']).map(mode=>({mode,shift:0}));
const crop=transfer?[5,12.5]:direction?[5,10.5]:null;
let compilerComparison;
if(transfer){
 const candidate=structuredClone(score);
 for(const c of candidate.chords)for(const target of targets){
  if(c.start===target.start)c.start+=.15;
  if(c.end===target.start)c.end+=.15;
 }
 const compiled=await json(`${api}/scores/playback/manifest`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(candidate)});
 assert.deepEqual(compiled.events.filter(e=>e.track!=='guitar'),manifest.events.filter(e=>e.track!=='guitar'));
 compilerComparison=targets.map(t=>{
  const next=compiled.events.find(e=>e.track==='guitar'&&e.source_id===t.source_id);
  assert.ok(next);return {symbol:t.symbol,boundary:t.start,requestedDelay:.15,firstStroke:next.start,actualDelay:next.start-t.start};
 });
}
const sourceHash=createHash('sha256').update(await readFile(path.join(root,'public/listening/ensemble-2026-10-18/source.wav'))).digest('hex');
const results=[];
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
 const page=await browser.newPage();await page.goto(`${ui}/listening/ensemble-2026-10-18/source.wav`);
 for(const {mode,shift} of variants){
  const move=t=>targets.some(e=>e.start===t)?t+shift:t;
  const variantBlocks=blocks.map(e=>({...e,start:move(e.start),end:move(e.end),sustain_end:move(e.sustain_end)}));
  const variantManifest=transfer?{...manifest,events:manifest.events.map(e=>e.track==='guitar'?{
   ...e,start:move(e.start),end:move(e.end),sustain_end:e.sustain_end==null?e.sustain_end:move(e.sustain_end),
  }:e)}:manifest;
  if(transfer){
   let changedStarts=0;
   for(let i=0;i<manifest.events.length;i++){
    const before=manifest.events[i],after=variantManifest.events[i];
    if(before.start!==after.start)changedStarts++;
    const {start:s1,end:e1,sustain_end:r1,...rest1}=before;
    const {start:s2,end:e2,sustain_end:r2,...rest2}=after;
    assert.deepEqual(rest1,rest2); // Same voices, offsets, strengths, stroke and identities.
    if(before.track!=='guitar')assert.deepEqual(before,after);
    assert.ok(after.end>after.start);
   }
   assert.equal(changedStarts,shift===0?0:2); // No extra brush and no downstream shift.
  }
  // All non-target boundaries are immutable, and no gap/overlap may be introduced.
  for(let i=0;i<blocks.length;i++){
   assert.equal(variantBlocks[i].start,move(blocks[i].start));
   assert.ok(variantBlocks[i].end>variantBlocks[i].start);
   if(i)assert.ok(Math.abs(variantBlocks[i-1].end-variantBlocks[i].start)<1e-8);
  }
  const result=await page.evaluate(async({score,manifest,blocks,start,end,mode,direction,transfer,crop})=>{
   const {createMetronomeVoice}=await import('/src/metronomeVoice.ts');
   const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
   const rate=22050,context=new OfflineAudioContext(1,Math.round((end-start)*rate),rate);
   const data=await (await fetch('/listening/ensemble-2026-10-18/source.wav')).arrayBuffer();
   const source=context.createBufferSource(),gain=context.createGain();source.buffer=await context.decodeAudioData(data);gain.gain.value=.45;source.connect(gain).connect(context.destination);source.start(0);
   const timings=[];
   if(mode==='beats')for(const b of score.beats.filter(b=>b.time>=start&&b.time<end)){
    createMetronomeVoice(context,b.time-start,b.beat===1,.8);timings.push(b.time-start);
   }
   if(mode==='guitar'||mode==='harmony'||direction||transfer){
    const events=(mode==='harmony'||direction?blocks:manifest.events).filter(e=>e.track==='guitar'&&(e.sustain_end??e.end)>start&&e.start<end);
    const buffers=await preparePluckedBuffers(context,events.flatMap(e=>e.pitches));
    for(const e of events)for(let i=0;i<e.pitches.length;i++){
     const onset=e.start+(e.pitch_offsets[i]??i*.012),at=Math.max(0,onset-start),until=Math.min(end,e.sustain_end??e.end)-start,age=Math.max(0,start-onset);
     const node=createPluckedVoice(context,buffers.get(e.pitches[i]),at,until,.24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),age,e.stroke);
     if(node)timings.push(at);
    }
   }
   const buffer=await context.startRendering();
   const samples=Array.from(crop?buffer.getChannelData(0).slice(crop[0]*rate,crop[1]*rate):buffer.getChannelData(0));
   let peak=0,sum=0;for(const sample of samples){peak=Math.max(peak,Math.abs(sample));sum+=sample*sample;}
   return {samples,peak,rms:Math.sqrt(sum/samples.length),timings,rate};
  },{score,manifest:variantManifest,blocks:variantBlocks,start,end,mode,direction,transfer,crop});
  assert.ok(result.peak<1&&result.rms>.01,`${mode}: clipping/silence`);
  assert.ok(result.timings.length>0&&result.timings.every(t=>t>=0&&t<end-start));
  if(mode==='beats')assert.deepEqual(result.timings,score.beats.filter(b=>b.time>=start&&b.time<end).map(b=>b.time-start));
  if(block){
   // Check actual voice creation, including carry-in; catches silently missing strings.
   const expected=variantBlocks.flatMap(e=>e.pitches.map(()=>Math.max(0,e.start-start)));
   assert.deepEqual(result.timings,expected);
  }
  if(direction)assert.equal(result.samples.length,5.5*result.rate);
  if(transfer){
   assert.equal(result.samples.length,7.5*result.rate);
   const expected=variantManifest.events.filter(e=>e.track==='guitar'&&(e.sustain_end??e.end)>start&&e.start<end).flatMap(e=>e.pitches.flatMap((_,i)=>{
    const onset=e.start+(e.pitch_offsets[i]??i*.012),at=Math.max(0,onset-start);
    return Math.max(0,start-onset)<4&&Math.min(end,e.sustain_end??e.end)-start>at?[at]:[];
   }));
   assert.deepEqual(result.timings,expected);
  }
  const wav=Buffer.alloc(44+result.samples.length*2);wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(result.rate,24);wav.writeUInt32LE(result.rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
  result.samples.forEach((v,i)=>wav.writeInt16LE(Math.round(v*32767),44+i*2));await writeFile(path.join(out,`${mode}.wav`),wav);
  results.push({mode,shift,frames:result.samples.length,rate:result.rate,sha256:createHash('sha256').update(wav).digest('hex'),peak:result.peak,rms:result.rms,eventCount:result.timings.length,timings:result.timings});
 }
}finally{await browser.close();}
assert.deepEqual(await json(`${api}/revisions/${encodeURIComponent(revision)}`),score);
assert.equal(createHash('sha256').update(await readFile(path.join(root,'public/listening/ensemble-2026-10-18/source.wav'))).digest('hex'),sourceHash);
await copyFile(path.join(root,transfer?'scripts/strum-transfer.html':direction?'scripts/harmony-direction.html':block?'scripts/harmony-block.html':'scripts/alignment-isolation.html'),path.join(out,'index.html'));
await writeFile(path.join(out,'report.json'),JSON.stringify({revision,start,end,sourceGain:.45,sourceHash,crop,compilerComparison,targetBoundaries:targets.map(e=>({symbol:e.symbol,time:e.start})),blockControl:block,blocks:block?blocks:undefined,sourceOffset:score.song.source_start_seconds,interpretation:transfer?'Evaluation manifest only: two first strums and preceding harmony cutoffs delayed 150ms. Other attacks, pitches, string offsets and original audio unchanged. Not the result of the current score compiler and not a saved revision.':'Diagnostic overlays; no correction and no accuracy claim. Only two chord boundaries change; original audio and remaining boundaries are fixed. Cannot establish chord identity or whole-passage correctness.',savedRevisionUnchanged:true,results},null,2));
console.log(JSON.stringify({out,results:results.map(({timings,...r})=>r)}));
