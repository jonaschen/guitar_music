// Render only the fixed excerpt, with sufficient preroll for existing resonance.
import {chromium} from '@playwright/test';
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const input=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]);
const manifest=JSON.parse(await readFile(path.join(input,'manifest.json'),'utf8'));
const packet=JSON.parse(await readFile(path.join(input,'packet.json'),'utf8'));
const events=manifest.events.filter(e=>e.track==='guitar'&&e.start<packet.end&&(e.sustain_end??e.end)>packet.start);
const origin=Math.min(packet.start,...events.map(e=>e.start)),rate=22050;
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
 const page=await browser.newPage();await page.goto('http://127.0.0.1:5173/');
 const rendered=await page.evaluate(async({events,origin,rate,start,end})=>{
  const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
  const ctx=new OfflineAudioContext(1,Math.ceil((end-origin+.3)*rate),rate);
  const buffers=await preparePluckedBuffers(ctx,events.flatMap(e=>e.pitches));
  const onsets=[];
  for(const e of events)for(let i=0;i<e.pitches.length;i++){
   const at=e.start+(e.pitch_offsets[i]??0),until=Math.min(end,e.sustain_end??e.end);
   if(createPluckedVoice(ctx,buffers.get(e.pitches[i]),at-origin,until-origin,.24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),0,e.stroke))onsets.push(at);
  }
  const data=(await ctx.startRendering()).getChannelData(0).slice(Math.round((start-origin)*rate),Math.round((end-origin)*rate));
  const bytes=new Uint8Array(data.buffer),chunks=[];
  for(let i=0;i<bytes.length;i+=32768)chunks.push(String.fromCharCode(...bytes.subarray(i,i+32768)));
  return {audio:btoa(chunks.join('')),onsets};
 },{events,origin,rate,start:packet.start,end:packet.end});
 assert.deepEqual(rendered.onsets,events.flatMap(e=>e.pitches.map((_,i)=>e.start+(e.pitch_offsets[i]??0))));
 await writeFile(path.join(input,'guitar.f32'),Buffer.from(rendered.audio,'base64'));
 await writeFile(path.join(input,'render-checks.json'),JSON.stringify({onsets:rendered.onsets,origin,exactManifestOnsets:true},null,2));
}finally{await browser.close();}
await mkdir(output,{recursive:false});
const mix=spawnSync(process.env.GUITARSCRIBE_PYTHON||'/home/jonas/.cache/guitarscribe-runtime/bin/python',[
 path.join(root,'../backend/scripts/mix_downbeat_review.py'),input,output
],{encoding:'utf8'});assert.equal(mix.status,0,mix.stderr);
await copyFile(path.join(root,'scripts/downbeat-review.html'),path.join(output,'index.html'));
await copyFile(path.join(input,'packet.json'),path.join(output,'packet.json'));
console.log('Rendered downbeat review:',output);
