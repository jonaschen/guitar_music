// Render fixed A/B excerpts with the product guitar voice. No analysis or DB writes.
import {chromium} from '@playwright/test';
import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const input=path.resolve(process.argv[2]),output=path.resolve(process.argv[3]);
await mkdir(output,{recursive:false});
const rows=JSON.parse(await readFile(path.join(input,'packet.json'),'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
 const page=await browser.newPage();await page.goto('http://127.0.0.1:5173/');
 for(const row of rows){
  const directory=path.join(input,String(row.number));
  for(const variant of ['a','b']){
   const manifest=JSON.parse(await readFile(path.join(directory,variant+'-manifest.json'),'utf8'));
   const events=manifest.events.filter(e=>e.track==='guitar');
   const rate=22050,duration=manifest.duration_seconds;
   const rendered=await page.evaluate(async({events,rate,duration,start,end})=>{
    const {preparePluckedBuffers,createPluckedVoice}=await import('/src/pluckedTone.ts');
    const ctx=new OfflineAudioContext(1,Math.round((duration+.35)*rate),rate);
    const buffers=await preparePluckedBuffers(ctx,events.flatMap(e=>e.pitches));
    const onsets=[];
    for(const e of events)for(let i=0;i<e.pitches.length;i++){
     const at=e.start+(e.pitch_offsets[i]??i*.012),until=Math.min(duration,e.sustain_end??e.end);
     if(createPluckedVoice(ctx,buffers.get(e.pitches[i]),at,until,.24*(e.pitch_velocities[i]??e.velocity)/127/Math.sqrt(e.pitches.length),0,e.stroke))onsets.push(at);
    }
    const audio=(await ctx.startRendering()).getChannelData(0);
    const excerpt=audio.slice(Math.round(start*rate),Math.round(end*rate));
    const bytes=new Uint8Array(excerpt.buffer),chunks=[];
    for(let i=0;i<bytes.length;i+=32768)chunks.push(String.fromCharCode(...bytes.subarray(i,i+32768)));
    return {audio:btoa(chunks.join('')),onsets};
   },{events,rate,duration,start:row.start,end:row.end});
   const expected=events.flatMap(e=>e.pitches.flatMap((_,i)=>{const at=e.start+(e.pitch_offsets[i]??i*.012);return at<Math.min(duration,e.sustain_end??e.end)?[at]:[]}));
   assert.deepEqual(rendered.onsets,expected);
   await writeFile(path.join(directory,variant+'.f32'),Buffer.from(rendered.audio,'base64'));
  }
  const result=spawnSync(process.env.GUITARSCRIBE_PYTHON||'/home/jonas/.cache/guitarscribe-runtime/bin/python',[
   path.join(root,'../backend/scripts/mix_performance_review.py'),directory,output,String(row.number)
  ],{encoding:'utf8'});assert.equal(result.status,0,result.stderr);
  console.log('Rendered group',row.number);
 }
}finally{await browser.close();}
await writeFile(path.join(output,'packet.json'),JSON.stringify(rows,null,2));
await copyFile(path.join(root,'scripts/performance-review.html'),path.join(output,'index.html'));
