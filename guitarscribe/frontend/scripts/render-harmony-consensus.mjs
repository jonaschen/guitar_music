// Render the pinned acoustic-consensus candidate with the product's guitar voice.
import {chromium} from '@playwright/test';
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const evaluation=path.resolve(root,'../output/evaluation/lyric-anchor-capture-2026-10-23');
const packet=path.join(evaluation,'packet'), candidate=path.join(evaluation,'acoustic-candidate');
const config=JSON.parse(await readFile(path.join(packet,'config.json'),'utf8'));
const base=JSON.parse(await readFile(path.join(packet,'manifest.json'),'utf8'));
const revised=JSON.parse(await readFile(path.join(candidate,'manifest.json'),'utf8'));
const output=path.join(root,'public/listening/harmony-consensus-2026-10-23');
await mkdir(output,{recursive:false});
const sourceData=await readFile(path.join(packet,'audio.wav'));
assert.equal(createHash('sha256').update(sourceData).digest('hex'),config.audio_sha256);
await writeFile(path.join(output,'source.wav'),sourceData);
const start=61,end=77,rate=22050,tail=.35,frames=Math.round((end-start+tail)*rate);
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']}),results=[];
try{
 const page=await browser.newPage();await page.goto('http://127.0.0.1:5173/');
 for(const [label,manifest] of [['original',null],['before',base],['candidate',revised]]){
  const events=(manifest?.events??[]).filter(e=>e.track==='guitar'&&(e.sustain_end??e.end)>start&&e.start<end);
  const result=await page.evaluate(async({events,start,end,rate,frames,sourceStart})=>{
   const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
   const context=new OfflineAudioContext(1,frames,rate);
   const source=context.createBufferSource(),gain=context.createGain();
   source.buffer=await context.decodeAudioData(await(await fetch('/listening/harmony-consensus-2026-10-23/source.wav')).arrayBuffer());
   gain.gain.value=.45;gain.gain.setValueAtTime(.45,end-start-.04);gain.gain.linearRampToValueAtTime(0,end-start);
   source.connect(gain).connect(context.destination);source.start(0,start-sourceStart,end-start);
   const buffers=await preparePluckedBuffers(context,events.flatMap(e=>e.pitches)),timings=[];
   for(const e of events)for(let i=0;i<e.pitches.length;i++){
    const onset=e.start+(e.pitch_offsets[i]??i*.012),at=Math.max(0,onset-start),age=Math.max(0,start-onset);
    if(createPluckedVoice(context,buffers.get(e.pitches[i]),at,Math.min(end,e.sustain_end??e.end)-start,
      .24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),age,e.stroke))timings.push(at);
   }
   const rendered=await context.startRendering(),samples=Array.from(rendered.getChannelData(0));
   let peak=0,sum=0;for(const v of samples){peak=Math.max(peak,Math.abs(v));sum+=v*v;}
   return {samples,timings,peak,rms:Math.sqrt(sum/samples.length)};
  },{events,start,end,rate,frames,sourceStart:config.analysis_start});
  const expected=events.flatMap(e=>e.pitches.flatMap((_,i)=>{const t=e.start+(e.pitch_offsets[i]??i*.012);return Math.max(0,start-t)<4&&Math.min(end,e.sustain_end??e.end)-start>Math.max(0,t-start)?[Math.max(0,t-start)]:[];}));
  assert.deepEqual(result.timings,expected);assert.ok(result.peak<1&&result.rms>.01);
  assert.ok(result.samples.slice(-500).every(v=>Math.abs(v)<1/32767));
  const wav=Buffer.alloc(44+result.samples.length*2);wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(rate,24);wav.writeUInt32LE(rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
  result.samples.forEach((v,i)=>wav.writeInt16LE(Math.round(v*32767),44+i*2));await writeFile(path.join(output,`${label}.wav`),wav);
  results.push({label,frames:result.samples.length,peak:result.peak,rms:result.rms,voices:result.timings.length,sha256:createHash('sha256').update(wav).digest('hex')});
 }
}finally{await browser.close();}
await copyFile(path.join(root,'scripts/harmony-consensus.html'),path.join(output,'index.html'));
await writeFile(path.join(output,'report.json'),JSON.stringify({config_id:config.config_id,base_revision:base.revision,candidate_revision:revised.revision,range:[start,end],source_gain:.45,guitar_gain:.24,results},null,2));
console.log(JSON.stringify({output,results}));
