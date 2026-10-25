// Render fixed third-source G notes with the same tone used in the prior comparison.
import { chromium } from '@playwright/test';
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const input=path.resolve(root,'../output/evaluation/third-source-2026-10-25');
const output=path.join(root,'public/listening/third-source-2026-10-25');
const manifest=JSON.parse(await readFile(path.join(input,'report.json'),'utf8'));
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
const results=[],groups=[];
try {
 const page=await browser.newPage(); await page.goto('http://127.0.0.1:5173/');
 for(let i=1;i<=2;i++) {
  const meta=manifest.cases[i-1],duration=meta.duration;
  for(const label of ['source','vocal']) {
   const file=`${label}-${i}.wav`,source=await readFile(path.join(input,file));
   assert.equal(createHash('sha256').update(source).digest('hex'),meta.audio[label].sha256);
   await copyFile(path.join(input,file),path.join(output,file));
  }
  for(const label of ['g']) {
   const data=JSON.parse(await readFile(path.join(input,`${label}-${i}.json`),'utf8'));
   const notes=Array.isArray(data)?data:data.notes;
   assert.ok(Array.isArray(notes)&&notes.length>0);
   for(const n of notes)assert.ok(Number.isFinite(n.start+n.end+n.midi)&&n.end>n.start&&n.start>=0&&n.end<=duration+.02);
   const result=await page.evaluate(async({notes,duration})=>{
    const {melodyPhrases,playMelodyPhrase}=await import('/src/connectedMelody.ts');
    const rate=44100,lead=.01,frames=Math.round(duration*rate);
    const context=new OfflineAudioContext(1,frames+441,rate);
    // Equal velocity and per-voice gain. Preserve all detected voices and rests.
    const phrases=melodyPhrases(notes.map(n=>({start:n.start,end:n.end,midi:n.midi})));
    let voices=0;
    for(const phrase of phrases)if(playMelodyPhrase(context,phrase,{scoreStart:0,scoreEnd:duration,contextStart:lead,rate:1,peak:.12,type:'triangle'}))voices++;
    const buffer=await context.startRendering();
    const samples=Array.from(buffer.getChannelData(0).slice(441));
    let peak=0,sum=0;for(const s of samples){peak=Math.max(peak,Math.abs(s));sum+=s*s;}
    return {samples,peak,rms:Math.sqrt(sum/samples.length),voices,frames};
   },{notes,duration});
   assert.equal(result.samples.length,result.frames);assert.ok(result.peak<.98&&result.rms>.001);
   const wav=Buffer.alloc(44+result.frames*2);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(44100,24);wav.writeUInt32LE(88200,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
   result.samples.forEach((v,j)=>wav.writeInt16LE(Math.round(v*32767),44+j*2));
   const file=`${label}-${i}.wav`;await writeFile(path.join(output,file),wav);
   const {samples,...stats}=result;results.push({file,notes:notes.length,...stats,sha256:createHash('sha256').update(wav).digest('hex')});
  }
  groups.push({id:`clip-${i}`,title:`第 ${i} 段：原曲 ${meta.start}–${meta.end} 秒`,question:'先聽原曲、分離人聲，再聽 G 旋律：音高與拍長是否接近？是否仍明顯零落？',tracks:[{label:'原曲',file:`source-${i}.wav`},{label:'分離人聲',file:`vocal-${i}.wav`},{label:'G 旋律',file:`g-${i}.wav`}]});
 }
}finally{await browser.close();}
await copyFile(path.join(root,'scripts/source-checkpoint.html'),path.join(output,'index.html'));
await writeFile(path.join(output,'packet.json'),JSON.stringify({groups},null,2));
const report={status:'awaiting_human_comparison',job_id:manifest.job_id,decoder_sha256:manifest.decoder_sha256,tone:'same product connectedMelody triangle as previous A',peak_per_voice:.12,velocity:'constant',lead_removed_seconds:.01,notes_filtered:false,time_warp:false,results};
await writeFile(path.join(output,'render-report.json'),JSON.stringify(report,null,2));
await writeFile(path.join(input,'render-report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({output,report},null,2));
