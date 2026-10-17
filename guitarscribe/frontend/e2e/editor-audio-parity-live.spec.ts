import {writeFileSync} from "node:fs";
import {test,expect} from "@playwright/test";
import type {SongScore} from "../src/types";

test("saved G deep link survives refresh and editor schedules its exact pitches and timing",async({page,request},testInfo)=>{
  const revision=process.env.GUITARSCRIBE_RECOVERY_REVISION;
  test.skip(!revision,"Explicit saved revision required; no persistence writes");
  test.setTimeout(120_000);
  const api=process.env.GUITARSCRIBE_API_URL??"http://127.0.0.1:8000";
  const ui=process.env.GUITARSCRIBE_UI_URL??"http://127.0.0.1:5173";
  const original:SongScore=await (await request.get(`${api}/revisions/${revision}`)).json();
  await page.addInitScript(()=>{
    localStorage.setItem("guitarscribe.workspaceMode","focus");
    const w=window as any;w.__contexts=[];w.__frequencies=[];w.__ends=[];
    w.AudioContext=class extends OfflineAudioContext{
      constructor(){super(1,22050*20,22050);w.__contexts.push(this);}
      resume(){return Promise.resolve();}
      createOscillator(){
        const s=super.createOscillator(),set=s.frequency.setValueAtTime.bind(s.frequency),stop=s.stop.bind(s);
        s.frequency.setValueAtTime=(v,t)=>{w.__frequencies.push([v,t]);return set(v,t);};
        s.stop=t=>{if(t!==undefined)w.__ends.push(t);stop(t);};return s;
      }
    };
  });
  const blocked:string[]=[];
  await page.route("**/*",route=>{
    const req=route.request(),path=new URL(req.url()).pathname;
    if(!["GET","HEAD","OPTIONS"].includes(req.method())&&path!=="/scores/musicxml"){
      blocked.push(path);return route.abort();
    }
    return route.continue();
  });
  await page.goto(`${ui}/?revision=${encodeURIComponent(revision!)}`);
  await expect(page.getByLabel("Current working version")).toContainText(revision!);
  await page.reload();
  await expect(page.getByLabel("Current working version")).toContainText(revision!);
  await expect(page.getByLabel("Editor melody version")).toContainText(`Contour G 候選 · ${original.melody.length}`);
  const bar=page.getByLabel("Tab start bar");
  const value=await bar.locator("option").evaluateAll(opts=>opts.find(o=>o.textContent?.startsWith("Bar 28 ·"))?.getAttribute("value"));
  await bar.selectOption(value!);await page.getByLabel("Tab bar count").selectOption("8");
  await page.getByLabel("Editor audition mode").selectOption("melody");
  await page.getByRole("button",{name:"重播所選小節",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__frequencies.length)).toBeGreaterThan(0);
  const start=original.beats.find(b=>b.measure===28&&b.beat===1)!.time;
  const end=original.beats.find(b=>b.measure===36&&b.beat===1)!.time;
  const notes=original.melody.filter(n=>n.end>start&&n.start<end);
  const actual=await page.evaluate(()=>({frequencies:(window as any).__frequencies as number[][],ends:(window as any).__ends as number[]}));
  actual.frequencies.sort((a,b)=>a[1]-b[1]);
  expect(actual.frequencies).toHaveLength(notes.length);
  notes.forEach((n,i)=>{
    expect(69+12*Math.log2(actual.frequencies[i][0]/440)).toBeCloseTo(n.midi,8);
    expect(actual.frequencies[i][1]).toBeCloseTo(Math.max(0,n.start-start)+.03,8);
  });
  const ends=notes.filter((n,i)=>!notes[i+1]||notes[i+1].start!==n.end||notes[i+1].midi===n.midi)
    .map(n=>Math.min(end,n.end)-start+.03).sort((a,b)=>a-b);
  expect(actual.ends.sort((a,b)=>a-b)).toHaveLength(ends.length);
  ends.forEach((e,i)=>expect(actual.ends[i]).toBeCloseTo(e,8));
  const samples=await page.evaluate(async()=>{
    const buffer=await (window as any).__contexts.at(-1).startRendering();
    const data=buffer.getChannelData(0) as Float32Array;
    return Array.from(data);
  });
  expect(Math.sqrt(samples.reduce((s,x)=>s+x*x,0)/samples.length)).toBeGreaterThan(.01);
  // Matched-level listening artifact from the actual App path, excluding its lead-in.
  const audio=samples.slice(Math.round(.03*22050),Math.round(.03*22050)+Math.round((end-start)*22050));
  const wav=Buffer.alloc(44+audio.length*2);
  wav.write("RIFF",0);wav.writeUInt32LE(wav.length-8,4);wav.write("WAVEfmt ",8);
  wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);
  wav.writeUInt32LE(22050,24);wav.writeUInt32LE(44100,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);
  wav.write("data",36);wav.writeUInt32LE(audio.length*2,40);
  audio.forEach((v,i)=>wav.writeInt16LE(Math.round(Math.max(-1,Math.min(1,v*1.875))*32767),44+i*2));
  writeFileSync(testInfo.outputPath("editor.wav"),wav);
  expect(blocked).toEqual([]);
  expect(await (await request.get(`${api}/revisions/${revision}`)).json()).toEqual(original);
});
