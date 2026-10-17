import { test, expect } from "@playwright/test";
import { melodyPhrases } from "../src/connectedMelody";

test("phrases preserve note data, real gaps, overlaps and repeated attacks", () => {
  const notes = [
    {start:0,end:.1,midi:60}, {start:.1,end:.2,midi:62},
    {start:.20000001,end:.3,midi:64}, {start:.3,end:.4,midi:64},
    {start:.35,end:.5,midi:67},
  ];
  const snapshot = structuredClone(notes);
  expect(melodyPhrases(notes).map(p=>p.length)).toEqual([2,1,1,1]);
  expect(melodyPhrases(notes).flat()).toEqual(snapshot);
  expect(notes).toEqual(snapshot);
});

test("offline audio removes internal dips while retaining rests, short endings and repeated attacks", async ({page}) => {
  await page.goto("/");
  const results = await page.evaluate(async()=>{
    const path="/src/connectedMelody.ts";
    const {melodyPhrases,playMelodyPhrase}=await import(path);
    const oldPath="/src/melodyEnvelope.ts";
    const {melodyEnvelope}=await import(oldPath);
    const notes=[{start:.1,end:.2,midi:69},{start:.2,end:.3,midi:71},{start:.3,end:.31,midi:72},{start:.4,end:.5,midi:72},{start:.5,end:.6,midi:72}];
    async function render(connected:boolean){
      const context=new OfflineAudioContext(1,48000,48000);
      if(connected) for(const phrase of melodyPhrases(notes)) playMelodyPhrase(context,phrase,{scoreStart:0,scoreEnd:1,contextStart:0,rate:1,peak:.3});
      else for(const n of notes){
        const s=context.createOscillator(),g=context.createGain();s.type="triangle";s.frequency.value=440*2**((n.midi-69)/12);
        const points=melodyEnvelope(n.start,n.end,.3);
        g.gain.setValueAtTime(points[0].value,points[0].time);g.gain.linearRampToValueAtTime(points[1].value,points[1].time);g.gain.linearRampToValueAtTime(points[2].value,points[2].time);g.gain.exponentialRampToValueAtTime(points[3].value,points[3].time);
        s.connect(g).connect(context.destination);s.start(n.start);s.stop(n.end);
      }
      const data=(await context.startRendering()).getChannelData(0);
      const rms=(a:number,b:number)=>{const v=data.slice(Math.round(a*48000),Math.round(b*48000));return Math.sqrt(v.reduce((s,v)=>s+v*v,0)/v.length);};
      return {boundary:rms(.195,.2),held:rms(.15,.18),rest:rms(.315,.395),end:rms(.605,.8),repeated:rms(.499,.501),peak:Math.max(...data.map(Math.abs))};
    }
    return {connected:await render(true),old:await render(false)};
  });
  expect(results.connected.boundary).toBeGreaterThan(results.connected.held*.6);
  expect(results.old.boundary).toBeLessThan(results.old.held*.1);
  expect(results.connected.rest).toBe(0);
  expect(results.connected.end).toBe(0);
  expect(results.connected.repeated).toBeLessThan(results.connected.held*.3);
  expect(results.connected.peak).toBeLessThan(.31);
});

test("resume and speed clip the phrase without replaying its prefix or extending its end", async ({page})=>{
  await page.goto("/");
  const result=await page.evaluate(async()=>{
    const path="/src/connectedMelody.ts";const {playMelodyPhrase}=await import(path);
    const c=new OfflineAudioContext(1,48000,48000);
    const frequencies:Array<[number,number]>=[];
    const create=c.createOscillator.bind(c);
    c.createOscillator=()=>{const s=create(),set=s.frequency.setValueAtTime.bind(s.frequency);s.frequency.setValueAtTime=(v,t)=>{frequencies.push([v,t]);return set(v,t);};return s;};
    playMelodyPhrase(c,[{start:0,end:.2,midi:60},{start:.2,end:.4,midi:69},{start:.4,end:.6,midi:72}],{scoreStart:.3,scoreEnd:.5,contextStart:.1,rate:2,peak:.3});
    const data=(await c.startRendering()).getChannelData(0);
    return {frequencies,before:data.slice(0,4700).every(v=>v===0),after:data.slice(9700).every(v=>v===0)};
  });
  expect(result.frequencies[0][0]).toBeCloseTo(440,8);
  expect(result.frequencies[0][1]).toBeCloseTo(.1,8);
  expect(result.frequencies[1][1]).toBeCloseTo(.15,8);
  expect(result.before).toBe(true);expect(result.after).toBe(true);
});


test("a sub-millisecond boundary note keeps its velocity change at its own onset", async ({page}) => {
  await page.goto("/");
  const values = await page.evaluate(async () => {
    const path = "/src/connectedMelody.ts"; const {playMelodyPhrase} = await import(path);
    const context = new OfflineAudioContext(1,48000,48000);
    const points: Array<[number,number]> = [];
    const create = context.createGain.bind(context);
    context.createGain = () => {
      const gain = create(), set = gain.gain.setValueAtTime.bind(gain.gain);
      gain.gain.setValueAtTime = (value,time) => { points.push([value,time]); return set(value,time); };
      return gain;
    };
    playMelodyPhrase(context,[{start:.1,end:.2,midi:60,velocity:127},{start:.2,end:.201,midi:62,velocity:64}],{scoreStart:0,scoreEnd:1,contextStart:0,rate:1,peak:1});
    await context.startRendering();
    return points;
  });
  const quiet = values.filter(([v]) => v > 0 && v < 1);
  expect(quiet.length).toBeGreaterThan(0);
  expect(quiet.every(([,t]) => t >= .2)).toBe(true);
});
