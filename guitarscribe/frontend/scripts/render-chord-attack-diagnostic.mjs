// Same product voice and rhythm; only chord-boundary assignment differs.
import {chromium} from '@playwright/test';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const input=process.argv[2]?path.resolve(process.argv[2]):path.join(root,'../output/evaluation/chord-attack-diagnostic-2026-10-26-verified');
const slug=process.argv[3]??'chord-attack-2026-10-26';
assert.match(slug,/^[a-z0-9-]+$/);
const output=path.join(root,'public/listening',slug);
await mkdir(output,{recursive:false});
const audit=JSON.parse(await readFile(path.join(input,'report.json'),'utf8'));
const source=await readFile(path.join(input,'source.wav'));
assert.equal(createHash('sha256').update(source).digest('hex'),audit.source_sha256);
await writeFile(path.join(output,'source.wav'),source);
const manifests=await Promise.all(['A','B'].map(async label=>JSON.parse(await readFile(path.join(input,`${label}-manifest.json`),'utf8'))));
const [start,end]=audit.window,duration=end-start,rate=22050,frames=Math.round((duration+.35)*rate);
assert.ok(Number.isFinite(duration)&&duration>0);
const events=manifests.map(m=>m.events.filter(e=>e.track==='guitar'&&(e.sustain_end??e.end)>start&&e.start<end));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
let rendered;
try {
 const page=await browser.newPage();await page.goto('http://localhost:5173/');
 rendered=await page.evaluate(async({events,start,end,duration,rate,frames,slug})=>{
  const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
  const waves=[],timings=[];
  for(const list of events){
   const ctx=new OfflineAudioContext(1,frames,rate),buffers=await preparePluckedBuffers(ctx,list.flatMap(e=>e.pitches)),onsets=[];
   for(const e of list)for(let i=0;i<e.pitches.length;i++){
    const onset=e.start+(e.pitch_offsets[i]??0)-start,at=Math.max(0,onset),age=Math.max(0,-onset),until=Math.min(end,e.sustain_end??e.end)-start;
    if(createPluckedVoice(ctx,buffers.get(e.pitches[i]),at,until,.24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),age,e.stroke))onsets.push(at);
   }
   waves.push((await ctx.startRendering()).getChannelData(0));timings.push(onsets);
  }
  const ctx=new OfflineAudioContext(1,frames,rate),node=ctx.createBufferSource(),gain=ctx.createGain();
  node.buffer=await ctx.decodeAudioData(await(await fetch(`/listening/${slug}/source.wav`)).arrayBuffer());
  gain.gain.setValueAtTime(.45,0);gain.gain.setValueAtTime(.45,duration-.04);gain.gain.linearRampToValueAtTime(0,duration);
  node.connect(gain).connect(ctx.destination);node.start(0,0,duration);
  const original=(await ctx.startRendering()).getChannelData(0);
  const rms=x=>Math.sqrt(x.slice(0,Math.round(duration*rate)).reduce((s,v)=>s+v*v,0)/(duration*rate));
  const originalRms=rms(original),guitarRms=waves.map(rms);
  // One common gain for both candidates, to keep guitar audible against the mix.
  const guitarGain=.75*originalRms/Math.max(...guitarRms);
  const mixed=waves.map(w=>Float32Array.from(w,(v,i)=>original[i]+v*guitarGain));
  let peak=0;for(const w of mixed)for(const v of w)peak=Math.max(peak,Math.abs(v));
  const commonGain=Math.min(1,.95/Math.max(peak,1e-12));
  return {samples:mixed.map(w=>Array.from(w,v=>v*commonGain)),timings,sourceGain:.45,guitarGain,commonGain,originalRms,guitarRms};
 },{events,start,end,duration,rate,frames,slug});
}finally{await browser.close();}
const outputs=[];
for(let i=0;i<2;i++){
 const expected=events[i].flatMap(e=>e.pitches.flatMap((_,j)=>{
  const onset=e.start+(e.pitch_offsets[j]??0)-start;
  return Math.max(0,-onset)<4&&Math.min(end,e.sustain_end??e.end)-start>Math.max(0,onset)?[Math.max(0,onset)]:[];
 }));
 assert.deepEqual(rendered.timings[i],expected);
 const values=rendered.samples[i];assert.equal(values.length,frames);
 assert.ok(values.every(v=>Number.isFinite(v)&&Math.abs(v)<1));
 assert.ok(values.slice(-500).every(v=>Math.abs(v)<1/32767));
 const wav=Buffer.alloc(44+2*frames);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(rate,24);wav.writeUInt32LE(rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(frames*2,40);
 values.forEach((v,j)=>wav.writeInt16LE(Math.round(v*32767),44+j*2));
 let published=wav;
 if(i===0&&audit.reference_A_sha256){
  const reference=await readFile(path.join(input,'A-reference.wav'));
  assert.equal(createHash('sha256').update(reference).digest('hex'),audit.reference_A_sha256);
  assert.equal(reference.length,wav.length);assert.deepEqual(reference.subarray(0,44),wav.subarray(0,44));
  // Browser float arithmetic may change final PCM rounding by one unit.
  // Require numerical parity before reusing the exact human-reviewed control.
  for(let j=44;j<wav.length;j+=2)assert.ok(Math.abs(reference.readInt16LE(j)-wav.readInt16LE(j))<=1);
  published=reference;
 }
 const label=['A','B'][i];await writeFile(path.join(output,`${label}.wav`),published);
 let peak=0;for(const v of values)peak=Math.max(peak,Math.abs(v));
 outputs.push({label,frames,voices:expected.length,peak,sha256:createHash('sha256').update(published).digest('hex'),reusedFrozenReference:published!==wav});
}
assert.notEqual(outputs[0].sha256,outputs[1].sha256);
const {samples,timings,...levels}=rendered;
await writeFile(path.join(input,'render-report.json'),JSON.stringify({outputs,levels,rate,duration,tail:.35,voice:'product pluckedTone',timingParity:true,onlyGuitarAndOriginal:true},null,2));
const template=process.argv[4]?path.resolve(process.argv[4]):path.join(root,'scripts/chord-attack.html');
const html=(await readFile(template,'utf8')).replace('每段 30 秒，後面約 18–28 秒較值得留意。',audit.listening_hint??'每段 30 秒，後面約 18–28 秒較值得留意。');
await writeFile(path.join(output,'index.html'),html);
console.log(JSON.stringify({outputs,levels}));
