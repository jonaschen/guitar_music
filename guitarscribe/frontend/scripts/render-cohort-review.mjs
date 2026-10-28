// Frozen previews use the same manifest and guitar voice as their workspaces.
import {chromium} from '@playwright/test';
import {readFile, writeFile, mkdir, copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const input=path.resolve(process.argv[2]);
const slug=process.argv[3];
assert.match(slug,/^[a-z0-9-]+$/);
const output=path.join(root,'public/listening',slug);
await mkdir(output,{recursive:false});
const reports=JSON.parse(await readFile(path.join(input,'report.json'),'utf8'));
const sha=data=>createHash('sha256').update(data).digest('hex');
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const results=[];
try {
 const page=await browser.newPage();
 await page.goto('http://127.0.0.1:5173/');
 for(const report of reports){
  const directory=path.join(input,`song-${report.number}`);
  const source=await readFile(path.join(directory,'source.wav'));
  assert.equal(sha(source),report.source_sha256);
  const sourceName=`song-${report.number}-input.wav`;
  await writeFile(path.join(output,sourceName),source);
  const manifest=JSON.parse(await readFile(path.join(directory,'manifest.json'),'utf8'));
  const score=JSON.parse(await readFile(path.join(directory,'score.json'),'utf8'));
  const response=await fetch(`http://127.0.0.1:8000/revisions/${report.revision}`);
  assert.ok(response.ok);assert.deepEqual(await response.json(),score);
  const compiled=await fetch('http://127.0.0.1:8000/scores/playback/manifest',{
   method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(score)});
  assert.ok(compiled.ok);assert.deepEqual(await compiled.json(),manifest);
  const events=manifest.events.filter(e=>e.track==='guitar');
  const duration=report.duration,rate=22050,frames=Math.round((duration+.35)*rate);
  const render=await page.evaluate(async({events,duration,rate,frames,url})=>{
   const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
   const context=new OfflineAudioContext(1,frames,rate);
   const buffers=await preparePluckedBuffers(context,events.flatMap(e=>e.pitches));
   const onsets=[];
   for(const e of events)for(let i=0;i<e.pitches.length;i++){
    const onset=e.start+(e.pitch_offsets[i]??i*.012),until=Math.min(duration,e.sustain_end??e.end);
    if(createPluckedVoice(context,buffers.get(e.pitches[i]),onset,until,
      .24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),0,e.stroke))onsets.push(onset);
   }
   const guitar=(await context.startRendering()).getChannelData(0);
   const ctx=new OfflineAudioContext(1,frames,rate),node=ctx.createBufferSource(),gain=ctx.createGain();
   node.buffer=await ctx.decodeAudioData(await(await fetch(url)).arrayBuffer());
   if(Math.abs(node.buffer.duration-duration)>.01)throw Error('Source duration differs');
   gain.gain.setValueAtTime(0,0);gain.gain.linearRampToValueAtTime(.45,.005);
   gain.gain.setValueAtTime(.45,duration-.005);gain.gain.linearRampToValueAtTime(0,duration);
   node.connect(gain).connect(ctx.destination);node.start(0,0,duration);
   const original=(await ctx.startRendering()).getChannelData(0);
   return {guitar:Array.from(guitar),source:Array.from(original),onsets};
  },{events,duration,rate,frames,url:`/listening/${slug}/${sourceName}`});
  const expected=events.flatMap(e=>e.pitches.flatMap((_,i)=>{
   const at=e.start+(e.pitch_offsets[i]??i*.012);
   return Math.min(duration,e.sustain_end??e.end)>at?[at]:[];
  }));
  assert.deepEqual(render.onsets,expected);
  const waves={guitar:render.guitar,source:render.source,mix:render.source.map((v,i)=>v+render.guitar[i])};
  let peak=0;for(const wave of Object.values(waves))for(const value of wave)peak=Math.max(peak,Math.abs(value));
  const commonGain=Math.min(1,.95/Math.max(peak,1e-12)),audio={};
  for(const [mode,values] of Object.entries(waves)){
   assert.equal(values.length,frames);
   assert.ok(values.slice(-500).every(v=>Math.abs(v)<1/32767));
   const wav=Buffer.alloc(44+frames*2);
   wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);
   wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);
   wav.writeUInt32LE(rate,24);wav.writeUInt32LE(rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);
   wav.write('data',36);wav.writeUInt32LE(frames*2,40);
   let energy=0;
   values.forEach((v,i)=>{assert.ok(Number.isFinite(v));const pcm=Math.round(v*commonGain*32767);assert.ok(Math.abs(pcm)<=32767);wav.writeInt16LE(pcm,44+i*2);energy+=v*v;});
   const filename=`song-${report.number}-${mode}.wav`;
   await writeFile(path.join(output,filename),wav);
   audio[mode]={file:filename,sha256:sha(wav),rms:Math.sqrt(energy/frames)*commonGain};
  }
  assert.ok(audio.guitar.rms>0 && audio.source.rms>0);
  results.push({...report,audio,commonGain,rate,frames,voices:expected.length,
   workspace_manifest_verified:true,source_gain:.45,guitar_gain:.24});
 }
}finally{await browser.close();}
await writeFile(path.join(output,'packet.json'),JSON.stringify(results,null,2));
await copyFile(path.join(root,'scripts/cohort-review.html'),path.join(output,'index.html'));
await writeFile(path.join(input,'render-report.json'),JSON.stringify(results,null,2));
console.log(JSON.stringify(results.map(r=>({title:r.title,voices:r.voices,gain:r.commonGain,audio:r.audio}))));
