// Controlled tempo-spacing audition: source stays fixed; no pitch shifting or score writes.
import {chromium} from '@playwright/test';
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const api=process.env.GUITARSCRIBE_API_URL??'http://127.0.0.1:8000';
const ui=process.env.GUITARSCRIBE_UI_URL??'http://127.0.0.1:5173';
const read=async p=>JSON.parse(await readFile(path.join(root,p),'utf8'));
const config=await read('public/listening/ensemble-2026-10-18/config.json');
const recipe=await read('../output/evaluation/accepted-strum-2026-10-22/recipe.json');
const checkpoint=await read('../output/evaluation/accepted-strum-2026-10-22/manifest.json');
assert.equal(config.revision,recipe.revision);
async function json(url,options){const response=await fetch(url,options);assert.ok(response.ok,`${response.status}: ${url}`);return response.json();}
const scoreUrl=`${api}/revisions/${encodeURIComponent(recipe.revision)}`;
const score=await json(scoreUrl);
const base=await json(`${api}/scores/playback/manifest`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(score)});
assert.equal(base.revision,recipe.base_manifest_revision);
const move=t=>{const c=recipe.adjustments.find(c=>c.expected_start===t);return c?t+c.delay_seconds:t;};
const expected=new Map(base.events.map(e=>[e.id,e.track==='guitar'?{...e,start:move(e.start),end:move(e.end),sustain_end:e.sustain_end==null?e.sustain_end:move(e.sustain_end)}:e]));
assert.equal(checkpoint.events.length,expected.size);
for(const e of checkpoint.events)assert.deepEqual(e,expected.get(e.id));
const {start,end}=config,anchor=start+5,rate=22050;
const variants=[{label:'X',spacing:.96},{label:'Y',spacing:1.04},{label:'Z',spacing:1}];
// Include the same complete set of strokes in all variants, even when delayed beyond source end.
// Common duration allows the slowest harmony release + 350ms; never truncate a last string.
const renderSeconds=5+(end-anchor)*1.04+.35;
const fullFrames=Math.ceil(renderSeconds*rate),cropFrame=5*rate;
const original=checkpoint.events.filter(e=>e.track==='guitar'&&(e.sustain_end??e.end)>start&&e.start<end);
const sourcePath=path.join(root,'public/listening/ensemble-2026-10-18/source.wav');
const hash=data=>createHash('sha256').update(data).digest('hex');
const sourceHash=hash(await readFile(sourcePath));
const out=path.join(root,'public/listening/pace-probe-2026-10-22');
await mkdir(out,{recursive:true});
const results=[];
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
 const page=await browser.newPage();await page.goto(`${ui}/listening/ensemble-2026-10-18/source.wav`);
 for(const {label,spacing} of variants){
  const warp=t=>t<=anchor?t:anchor+(t-anchor)*spacing;
  const events=original.map(e=>({...e,start:warp(e.start),end:warp(e.end),sustain_end:warp(Math.min(end,e.sustain_end??e.end))}));
  for(let i=0;i<events.length;i++){
   const e=events[i],b=original[i];
   assert.deepEqual(e.pitches,b.pitches);assert.deepEqual(e.pitch_offsets,b.pitch_offsets);assert.deepEqual(e.pitch_velocities,b.pitch_velocities);
   assert.equal(e.stroke,b.stroke);assert.equal(e.velocity,b.velocity);
   assert.ok(e.sustain_end>e.start+Math.max(...e.pitch_offsets));
   if(i)assert.ok(e.start>events[i-1].start);
  }
  const r=await page.evaluate(async({events,start,end,rate,fullFrames,cropFrame})=>{
   const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
   const context=new OfflineAudioContext(1,fullFrames,rate);
   const data=await(await fetch('/listening/ensemble-2026-10-18/source.wav')).arrayBuffer();
   const source=context.createBufferSource(),gain=context.createGain();source.buffer=await context.decodeAudioData(data);
   gain.gain.value=.45;gain.gain.setValueAtTime(.45,end-start-.04);gain.gain.linearRampToValueAtTime(0,end-start);
   source.connect(gain).connect(context.destination);source.start(0);
   const buffers=await preparePluckedBuffers(context,events.flatMap(e=>e.pitches)),timings=[];
   for(const e of events)for(let i=0;i<e.pitches.length;i++){
    const onset=e.start+(e.pitch_offsets[i]??i*.012),at=Math.max(0,onset-start),age=Math.max(0,start-onset),until=e.sustain_end-start;
    if(createPluckedVoice(context,buffers.get(e.pitches[i]),at,until,.24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),age,e.stroke))timings.push(at);
   }
   const buffer=await context.startRendering(),samples=Array.from(buffer.getChannelData(0).slice(cropFrame));
   let peak=0,sum=0;for(const v of samples){peak=Math.max(peak,Math.abs(v));sum+=v*v;}
   return {samples,timings,peak,rms:Math.sqrt(sum/samples.length)};
  },{events,start,end,rate,fullFrames,cropFrame});
  const expectedTimes=events.flatMap(e=>e.pitches.flatMap((_,i)=>{
   const onset=e.start+(e.pitch_offsets[i]??i*.012);
   return Math.max(0,start-onset)<4?[Math.max(0,onset-start)]:[];
  }));
  assert.deepEqual(r.timings,expectedTimes);assert.equal(r.samples.length,fullFrames-cropFrame);
  assert.ok(r.peak<1&&r.rms>.01);
  assert.ok(r.samples.slice(-500).every(v=>Math.abs(v)<1/32767),'Tail must finish, not be cut');
  const wav=Buffer.alloc(44+r.samples.length*2);wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(rate,24);wav.writeUInt32LE(rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
  r.samples.forEach((v,i)=>wav.writeInt16LE(Math.round(v*32767),44+i*2));
  await writeFile(path.join(out,`${label}.wav`),wav);
  results.push({label,spacing,offsetAt4Seconds:4*(spacing-1),offsetAt7Seconds:7*(spacing-1),frames:r.samples.length,peak:r.peak,rms:r.rms,eventCount:r.timings.length,timings:r.timings,sha256:hash(wav)});
 }
}finally{await browser.close();}
assert.deepEqual(await json(scoreUrl),score);assert.equal(hash(await readFile(sourcePath)),sourceHash);
assert.ok(results.every(r=>r.eventCount===results[0].eventCount));
await copyFile(path.join(root,'scripts/pace-probe.html'),path.join(out,'index.html'));
await writeFile(path.join(out,'report.json'),JSON.stringify({revision:recipe.revision,candidateRevision:checkpoint.revision,anchor,start,end,sourceHash,sourceGain:.45,sourceFadeSeconds:.04,rate,results,interpretation:'Blind local tempo-spacing preference only; source fixed, string offsets and pitch unchanged. No psychological inference or automatic score correction.',savedRevisionUnchanged:true},null,2));
console.log(JSON.stringify({out,results:results.map(({timings,...r})=>r)}));
