// One harmony hypothesis only: retain D instead of the short Am. All rhythm slots stay fixed.
import {chromium} from '@playwright/test';
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const contextMode=process.argv.includes('--context');
const api=process.env.GUITARSCRIBE_API_URL??'http://127.0.0.1:8000',ui=process.env.GUITARSCRIBE_UI_URL??'http://127.0.0.1:5173';
const revision='db8c657e-62a5-4fad-a33e-cde25a9e1c0d';
async function json(url,options){const r=await fetch(url,options);assert.ok(r.ok,`${r.status}: ${url}`);return r.json();}
const score=await json(`${api}/revisions/${revision}`),candidate=structuredClone(score);
const reference=score.chords.find(c=>c.id==='chord-94');assert.equal(reference.symbol,'D');
const ids=['chord-96','chord-97'],changed=candidate.chords.filter(c=>ids.includes(c.id));
assert.equal(changed.length,2);assert.ok(changed.every(c=>c.symbol==='Am'));
assert.equal(changed[0].start,67.25659863945579);assert.equal(changed.at(-1).end,68.18539682539682);
for(const c of changed){c.symbol='D';c.shape_symbol=reference.shape_symbol;c.voicing_id=reference.voicing_id;c.available_voicings=structuredClone(reference.available_voicings);}
const compile=s=>json(`${api}/scores/playback/manifest`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});
const original=await compile(score),reduced=await compile(candidate);
assert.equal(original.revision,'d8f5d37756d58e6d');
assert.deepEqual(original.events.filter(e=>e.track!=='guitar'),reduced.events.filter(e=>e.track!=='guitar'));
const guitar=m=>m.events.filter(e=>e.track==='guitar');
// Chord names may merge, but no rhythmic attack may appear/disappear or move.
assert.deepEqual(guitar(original).map(e=>[e.start,e.stroke]),guitar(reduced).map(e=>[e.start,e.stroke]));
const baseEvents=guitar(original),newEvents=guitar(reduced);let pitchChanges=0;
for(let i=0;i<baseEvents.length;i++){
 const a=baseEvents[i],b=newEvents[i];
 if(a.start<reference.start||a.start>=changed.at(-1).end)assert.deepEqual(a,b);
 if(JSON.stringify(a.pitches)!==JSON.stringify(b.pitches)){
  pitchChanges++;assert.ok(a.start>=changed[0].start&&a.start<changed.at(-1).end);
 }
}
assert.ok(pitchChanges>0);
const sourceFolder=contextMode?'harmony-context-2026-10-23':'pace-continuation-2026-10-22';
const config=JSON.parse(await readFile(path.join(root,`public/listening/${sourceFolder}/config.json`),'utf8'));
assert.equal(config.revision,revision);
const start=config.start,cropStart=contextMode?score.beats.find(b=>b.measure===34&&b.beat===1).time:65.5,end=contextMode?config.end:70.5,rate=22050;
assert.ok(config.end>=end);const frames=Math.round((end-start+.35)*rate),cropFrame=Math.round((cropStart-start)*rate);
const sourcePath=path.join(root,`public/listening/${sourceFolder}/source.wav`),hash=v=>createHash('sha256').update(v).digest('hex');
const sourceHash=hash(await readFile(sourcePath));
const out=path.join(root,contextMode?`public/listening/${sourceFolder}`:'public/listening/harmony-count-2026-10-22');await mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true}),results=[];
try{
 const page=await browser.newPage();await page.goto(`${ui}/listening/${sourceFolder}/source.wav`);
 for(const [label,manifest] of (contextMode?[['original',original],['M',original],['N',reduced]]:[['M',original],['N',reduced]])){
  const events=label==='original'?[]:guitar(manifest).filter(e=>(e.sustain_end??e.end)>start&&e.start<end);
  const r=await page.evaluate(async({events,start,end,rate,frames,cropFrame,sourceFolder})=>{
   const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
   const context=new OfflineAudioContext(1,frames,rate);
   const source=context.createBufferSource(),gain=context.createGain();source.buffer=await context.decodeAudioData(await(await fetch(`/listening/${sourceFolder}/source.wav`)).arrayBuffer());
   gain.gain.value=.45;gain.gain.setValueAtTime(.45,end-start-.04);gain.gain.linearRampToValueAtTime(0,end-start);source.connect(gain).connect(context.destination);source.start(0);source.stop(end-start);
   const buffers=await preparePluckedBuffers(context,events.flatMap(e=>e.pitches)),timings=[];
   for(const e of events)for(let i=0;i<e.pitches.length;i++){
    const onset=e.start+(e.pitch_offsets[i]??i*.012),at=Math.max(0,onset-start),age=Math.max(0,start-onset);
    if(createPluckedVoice(context,buffers.get(e.pitches[i]),at,Math.min(end,e.sustain_end??e.end)-start,.24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),age,e.stroke))timings.push(at);
   }
   const buffer=await context.startRendering(),samples=Array.from(buffer.getChannelData(0).slice(cropFrame));
   let peak=0,sum=0;for(const v of samples){peak=Math.max(peak,Math.abs(v));sum+=v*v;}
   return {samples,timings,peak,rms:Math.sqrt(sum/samples.length)};
  },{events,start,end,rate,frames,cropFrame,sourceFolder});
  const expected=events.flatMap(e=>e.pitches.flatMap((_,i)=>{const t=e.start+(e.pitch_offsets[i]??i*.012);return Math.max(0,start-t)<4&&Math.min(end,e.sustain_end??e.end)-start>Math.max(0,t-start)?[Math.max(0,t-start)]:[];}));
  assert.deepEqual(r.timings,expected);assert.ok(r.peak<1&&r.rms>.01);assert.ok(r.samples.slice(-500).every(v=>Math.abs(v)<1/32767));
  const wav=Buffer.alloc(44+r.samples.length*2);wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(rate,24);wav.writeUInt32LE(rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
  r.samples.forEach((v,i)=>wav.writeInt16LE(Math.round(v*32767),44+i*2));await writeFile(path.join(out,`${label}.wav`),wav);
  results.push({label,manifestRevision:manifest.revision,frames:r.samples.length,peak:r.peak,rms:r.rms,voiceCount:r.timings.length,sha256:hash(wav)});
 }
}finally{await browser.close();}
assert.deepEqual(await json(`${api}/revisions/${revision}`),score);assert.equal(hash(await readFile(sourcePath)),sourceHash);
await copyFile(path.join(root,contextMode?'scripts/harmony-context.html':'scripts/harmony-count.html'),path.join(out,'index.html'));
await writeFile(path.join(out,'report.json'),JSON.stringify({revision,sourceHash,sourceGain:.45,crop:[cropStart,end],tail:.35,rate,changedRegionIds:ids,changedPitchStrokeCount:pitchChanges,results,savedRevisionUnchanged:true,interpretation:'M original Am, N extends D through the short Am span. Original rhythm timestamps and stroke count fixed; playable voicing/string count and harmony resonance change with chord identity. No tempo or time-shift corrections, not a saved revision.'},null,2));
console.log(JSON.stringify({out,pitchChanges,results}));
