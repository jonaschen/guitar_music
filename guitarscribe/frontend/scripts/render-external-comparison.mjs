// Fixed, unedited MIDI/G comparison. Requires inspected anthem-N.json inputs.
import { chromium } from '@playwright/test';
import { readFile, writeFile, mkdir, copyFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const input=path.resolve(root,'../output/evaluation/external-comparison-2026-10-25');
const output=path.join(root,'public/listening/external-checkpoint-2026-10-25');
const manifest=JSON.parse(await readFile(path.join(input,'manifest.json'),'utf8'));
await mkdir(output,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
const results=[],groups=[];
try {
 const page=await browser.newPage(); await page.goto('http://127.0.0.1:5173/');
 for(let i=1;i<=2;i++) {
  const meta=manifest.files[i-1];
  const external=JSON.parse(await readFile(path.join(input,`anthem-${i}.json`),'utf8'));
  const duration=Math.max(meta.duration,...external.map(n=>n.end))+.1;
  const source=await readFile(path.join(input,meta.file));
  assert.equal(createHash('sha256').update(source).digest('hex'),meta.sha256);
  await copyFile(path.join(input,meta.file),path.join(output,meta.file));
  for(const label of ['baseline','anthem']) {
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
  groups.push({id:`clip-${i}`,title:`第 ${i} 組：${i===1?'先前零落的新曲':'先前較自然的曲目'}`,question:'先聽原人聲，再比較 A、B：哪個更接近原人聲的音高、拍長與連貫性？都不好也請直接說。',tracks:[{label:'原人聲',file:`vocal-${i}.wav`},{label:'A',file:`baseline-${i}.wav`},{label:'B',file:`anthem-${i}.wav`}]});
 }
}finally{await browser.close();}
await copyFile(path.join(root,'scripts/onset-checkpoint.html'),path.join(output,'index.html'));
await writeFile(path.join(output,'packet.json'),JSON.stringify({groups},null,2));
const report={status:'awaiting_human_comparison',mapping:{A:'existing_G',B:'AnthemScore_6.3.0_exported_MIDI'},tone:'same product connectedMelody triangle',peak_per_voice:.12,velocity:'constant',lead_removed_seconds:.01,notes_filtered:false,time_warp:false,limits:['Existing G used full-song context; external used short vocal clips.','No ground truth; external result is not presumed better.','All external overlapping pitches and overhanging tails retained; both synthesized tracks padded to same duration.','Rounded timing option disabled, but CSV grid alignment means unquantized acoustic timing is not established.'],results};
await writeFile(path.join(output,'render-report.json'),JSON.stringify(report,null,2));
await writeFile(path.join(input,'render-report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({output,report},null,2));
