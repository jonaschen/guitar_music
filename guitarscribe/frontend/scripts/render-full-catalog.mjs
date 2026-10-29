// Full-length product-voice renders. No guessed beat grid for rejected sources.
import {chromium} from '@playwright/test';
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const input=path.resolve(process.argv[2]),slug=process.argv[3];assert.match(slug,/^[a-z0-9-]+$/);
const output=path.join(root,'public/listening',slug);await mkdir(output,{recursive:false});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const results=[];
try{
 const page=await browser.newPage();await page.goto('http://127.0.0.1:5173/');
 while(results.length<7){
  let rows=[];try{rows=JSON.parse(await readFile(path.join(input,'overview.json'),'utf8'))}catch(e){if(e.code!=='ENOENT')throw e}
  let progressed=false;
  for(const row of rows){
   if(results.some(r=>r.video===row.video))continue;
   assert.equal(createHash('sha256').update(await readFile(row.input)).digest('hex'),row.sha256);
   const directory=path.join(output,row.video);await mkdir(directory,{recursive:false});
   const rate=22050,frames=Math.round((row.duration+.35)*rate);
   console.log('RENDER',row.video,row.kind,Math.round(row.duration));
   const rendered=await page.evaluate(async({events,duration,rate,frames})=>{
    const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
    const ctx=new OfflineAudioContext(1,frames,rate),buffers=await preparePluckedBuffers(ctx,events.flatMap(e=>e.pitches));
    const onsets=[];
    for(const e of events)for(let i=0;i<e.pitches.length;i++){
     const at=e.start+(e.pitch_offsets[i]??i*.012),until=Math.min(duration,e.sustain_end??e.end);
     if(createPluckedVoice(ctx,buffers.get(e.pitches[i]),at,until,.24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),0,e.stroke))onsets.push(at);
    }
    const data=(await ctx.startRendering()).getChannelData(0);
    const bytes=new Uint8Array(data.buffer,data.byteOffset,data.byteLength),parts=[];
    for(let i=0;i<bytes.length;i+=32768)parts.push(String.fromCharCode(...bytes.subarray(i,i+32768)));
    return {base64:btoa(parts.join('')),onsets};
   },{events:row.events,duration:row.duration,rate,frames});
   const expected=row.events.flatMap(e=>e.pitches.flatMap((_,i)=>{const t=e.start+(e.pitch_offsets[i]??i*.012);return t<Math.min(row.duration,e.sustain_end??e.end)?[t]:[]}));
   assert.deepEqual(rendered.onsets,expected);
   const voicePath=path.join(input,row.video,'guitar.f32');await writeFile(voicePath,Buffer.from(rendered.base64,'base64'));
   const mixed=spawnSync('/home/jonas/.cache/guitarscribe-runtime/bin/python',[
    path.join(root,'../backend/scripts/mix_catalog_audio.py'),row.input,voicePath,directory,String(row.duration)],{encoding:'utf8',maxBuffer:1024*1024});
   assert.equal(mixed.status,0,mixed.stderr);
   const audio=JSON.parse(await readFile(path.join(directory,'audio-checks.json'),'utf8'));
   const {events,input:sourcePath,...publicRow}=row;
   results.push({...publicRow,audio,voices:expected.length});
   await writeFile(path.join(output,'packet.json'),JSON.stringify(results,null,2));
   console.log('READY',row.video,expected.length,'voices');progressed=true;
  }
  if(!progressed)await new Promise(r=>setTimeout(r,10000));
 }
}finally{await browser.close();}
await copyFile(path.join(root,'scripts/full-catalog.html'),path.join(output,'index.html'));
// Feedback is separate evidence; the page applies it only to matching audio hashes.
await copyFile(path.join(root,'../backend/fixtures/full-catalog-feedback-2026-10-30.json'),path.join(output,'feedback.json'));
await copyFile(path.join(root,'../backend/fixtures/full-catalog-workspaces-2026-10-30.json'),path.join(output,'workspaces.json'));
for(const row of results)if(row.kind==='unmetered'){
 const evidence=JSON.parse(await readFile(path.join(input,row.video,'timing-rejection.json'),'utf8'));
 row.timing_summary={};
 for(const n of evidence.beats_per_downbeat_interval)row.timing_summary[n]=(row.timing_summary[n]??0)+1;
}
await writeFile(path.join(output,'packet.json'),JSON.stringify(results,null,2));
await writeFile(path.join(input,'render-report.json'),JSON.stringify(results,null,2));
console.log('FULL CATALOG READY',output);
