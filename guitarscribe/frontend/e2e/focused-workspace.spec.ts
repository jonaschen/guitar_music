import { test, expect, type Page } from "@playwright/test";
import type { SongScore } from "../src/types";

const score = {
  schema_version: "1.0", song: { title: "Focus workflow", source_type: "local", duration_seconds: 16, source_start_seconds: 18 },
  analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: .5, warnings: [] },
  key_context: { source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" }, shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" }, transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true },
  guitar: { tuning: [40,45,50,55,59,64], tuning_name: "EADGBE", capo: 0, max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner", tab_preference: "balanced" },
  beats: Array.from({length: 32}, (_,i) => ({time: i*.5, beat: i%4+1, measure: Math.floor(i/4)+1, confidence: 1})),
  chords: [], melody: [{ id: "n1", start: 0, end: .5, midi: 60, note: "C4", confidence: .5, string: 2, fret: 1, edited: false, origin: "model" }],
  rhythm: { subdivision: 8, pattern_id: "", display: [], confidence: 0, label: "" },
  provenance: { beat_engine: "test", chord_engine: "test", melody_engine: "test", parameters: { melody_note_processing: "bounded-source-v1", candidate_source_job_id: "focus" } },
} as SongScore;

async function setup(page: Page, workingScore = score) {
  await page.addInitScript(() => localStorage.removeItem("guitarscribe.workspaceMode"));
  await page.route("**/api/v1/jobs/focus", route => route.fulfill({json:{id:"focus",status:"completed",progress:100,artifacts:["vocal-stem"],score:workingScore}}));
  await page.route("**/rhythm-patterns?*", route => route.fulfill({json:[]}));
  await page.route("**/scores/musicxml", route => route.fulfill({status:503,body:"Not used in focus mode"}));
  await page.goto("/?job=focus");
  await expect(page.getByRole("button", {name:"顯示完整工具",exact:true})).toBeVisible();
}

test("default focus keeps a single editor and preserves unapplied draft across tool modes", async ({page}) => {
  await setup(page);
  await expect(page.getByRole("button", {name:"Start analysis",exact:true})).toBeHidden();
  await expect(page.getByLabel("Tab start bar")).toBeVisible();
  await expect(page.getByText("Compiled score playback",{exact:true})).toBeHidden();
  await expect(page.getByRole("button", {name:"Add note",exact:true})).toBeHidden();
  await expect(page.getByLabel("音符重疊提示")).toBeHidden();
  await page.getByRole("button",{name:"Tab n1 C4 2弦1格",exact:true}).click();
  await page.getByLabel("Tab fret",{exact:true}).fill("3");
  await expect(page.getByText(/音符草稿尚未套用/)).toBeVisible();
  await page.getByRole("button",{name:"顯示完整工具",exact:true}).click();
  await expect(page.getByRole("button", {name:"Start analysis",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"回到專注修譜",exact:true}).click();
  await expect(page.getByLabel("Tab fret",{exact:true})).toHaveValue("3");
  await expect(page.locator(".melody-editor")).toHaveCount(1);
  await expect(page.getByLabel("Current working version")).not.toContainText("有未保存修改");
  await page.screenshot({path:test.info().outputPath("focused-workspace.png"),fullPage:true});
});

test("focus edits, compiles, undoes, saves a new revision and explicitly restores it after refresh", async ({page}) => {
  let saved: SongScore | undefined;
  const compiled: SongScore[] = [];
  await page.route("**/scores/melody/edit", route => {
    const body = route.request().postDataJSON();
    const next = structuredClone(body.score);
    next.melody[0] = {...next.melody[0],midi:62,note:"D4",fret:3,edited:true};
    return route.fulfill({json:{score:next,selected_note_id:"n1"}});
  });
  await page.route("**/scores/playback/manifest",route=>{
    const body = route.request().postDataJSON(); compiled.push(body);
    return route.fulfill({json:{events:body.melody.map((n:any)=>({track:"melody",start:n.start,end:n.end,pitches:[n.midi],velocity:96}))}});
  });
  await page.route("**/revisions", route=>{
    const body=route.request().postDataJSON(); expect(body.create_new).toBe(true); saved=body.score;
    return route.fulfill({json:{revision_id:"focus-saved"}});
  });
  await page.route("**/revisions/focus-saved",route=>route.fulfill({json:saved}));
  await setup(page);
  await page.getByRole("button",{name:"Tab n1 C4 2弦1格",exact:true}).click();
  await page.getByLabel("Tab fret",{exact:true}).fill("3");
  await page.getByRole("button",{name:"Apply note",exact:true}).click();
  await expect(page.getByLabel("Current working version")).toContainText("有未保存修改");
  await page.getByLabel("Tab fret",{exact:true}).focus();
  await page.keyboard.press("Control+z");
  await expect(page.getByRole("button",{name:"Tab n1 D4 2弦3格",exact:true})).toBeVisible();
  await page.getByLabel("Editor audition mode").selectOption("ensemble");
  await page.getByRole("button",{name:"重播所選小節",exact:true}).click();
  await expect.poll(()=>compiled.length).toBe(1);
  expect(compiled[0].melody[0].midi).toBe(62);
  await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
  await page.getByRole("button",{name:"Undo melody edit",exact:true}).click();
  await expect(page.getByRole("button",{name:"Tab n1 C4 2弦1格",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Redo melody edit",exact:true}).click();
  await page.getByRole("button",{name:"保存目前工作版本",exact:true}).click();
  await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：focus-saved");
  await page.reload();
  await page.getByRole("button",{name:"恢復上次保存版本",exact:true}).click();
  await page.getByRole("button",{name:"確認恢復版本（可 Undo）",exact:true}).click();
  await expect(page.getByRole("button",{name:"Tab n1 D4 2弦3格",exact:true})).toBeVisible();
  expect(saved?.provenance.parameters?.candidate_source_job_id).toBe("focus");
});

test("source loading can be cancelled by changing tracks without stale playback", async ({page}) => {
  await page.addInitScript(()=>{
    (window as any).__played=[];
    Object.defineProperty(HTMLMediaElement.prototype,"readyState",{get(){return 0;}});
    HTMLMediaElement.prototype.play=function(){(window as any).__played.push(this.src);this.dispatchEvent(new Event("play"));return Promise.resolve();};
    HTMLMediaElement.prototype.pause=function(){this.dispatchEvent(new Event("pause"));};
  });
  await page.route("**/api/v1/jobs/focus/audio",()=>{});
  await page.route("**/api/v1/jobs/focus/artifacts/*",()=>{});
  await setup(page);
  await page.getByRole("button",{name:"對照來源片段",exact:true}).click();
  await expect(page.getByLabel("Editor playback status")).toContainText("載入來源中");
  await page.evaluate(()=>{(window as any).__oldAudio=document.querySelector("audio");});
  await page.getByLabel("Editor source track").selectOption("vocal-stem");
  await page.evaluate(()=>{(window as any).__oldAudio.dispatchEvent(new Event("loadedmetadata"));});
  expect(await page.evaluate(()=>(window as any).__played)).toEqual([]);
  await page.getByLabel("Editor playback speed").selectOption("0.75");
  await page.getByRole("button",{name:"對照來源片段",exact:true}).click();
  await page.locator("audio").evaluate(audio=>audio.dispatchEvent(new Event("loadedmetadata")));
  await expect.poll(()=>page.evaluate(()=>(window as any).__played.length)).toBe(1);
  expect(await page.locator("audio").evaluate((audio:HTMLAudioElement)=>audio.playbackRate)).toBe(.75);
  await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
});

test("source failure is explained in focus mode and leaves the score editable", async ({page}) => {
  await page.route("**/api/v1/jobs/focus/audio", route=>route.fulfill({status:404,body:"expired audio"}));
  await setup(page);
  await page.getByRole("button",{name:"對照來源片段",exact:true}).click();
  await expect(page.getByText("來源音訊無法載入，請確認來源仍可用或改聽工作譜。",{exact:true})).toBeVisible();
  await expect(page.getByLabel("Editor playback status")).toContainText("已暫停");
  await page.getByRole("button",{name:"Tab n1 C4 2弦1格",exact:true}).click();
  await expect(page.getByRole("button",{name:"Apply note",exact:true})).toBeEnabled();
  await expect(page.getByLabel("Current working version")).not.toContainText("有未保存修改");
});


test("connection switch cancels sound and compares the same score in solo and ensemble", async ({page}) => {
  await page.addInitScript(() => {
    const state = {started:0, stopped:0}; (window as any).__tones = state;
    const create = AudioContext.prototype.createOscillator;
    AudioContext.prototype.createOscillator = function() {
      const node = create.call(this), start = node.start.bind(node), stop = node.stop.bind(node);
      node.start = time => { state.started++; start(time); };
      node.stop = time => { if (time === undefined || time <= this.currentTime) state.stopped++; stop(time); };
      return node;
    };
  });
  const workingScore = structuredClone(score);
  workingScore.melody = [0,1,2].map(i => ({...score.melody[0], id:`n${i+1}`,start:i*.1,end:(i+1)*.1,midi:60+i*2}));
  // Exact adjacency independent of binary multiplication rounding.
  workingScore.melody[1].end = workingScore.melody[2].start;
  const compiled: SongScore[] = [];
  await page.route("**/scores/playback/manifest", route => {
    const body = route.request().postDataJSON(); compiled.push(body);
    return route.fulfill({json:{events:body.melody.map((n:any) => ({track:"melody",start:n.start,end:n.end,pitches:[n.midi],velocity:96,pitch_velocities:[96],pitch_offsets:[0]}))}});
  });
  await setup(page, workingScore);
  const connection = page.getByLabel("Melody connection");
  await expect(connection).toHaveValue("connected");
  for (const mode of ["melody", "ensemble"]) {
    await page.getByLabel("Editor audition mode").selectOption(mode);
    for (const [option, count] of [["connected",1],["separate",3]] as const) {
      await connection.selectOption(option);
      await page.evaluate(() => { (window as any).__tones.started = 0; });
      await page.getByRole("button",{name:"重播所選小節",exact:true}).click();
      await expect.poll(() => page.evaluate(() => (window as any).__tones.started)).toBe(count);
      await page.getByRole("button",{name:"暫停，保留位置",exact:true}).click();
    }
  }
  expect(compiled).toHaveLength(2);
  expect(compiled[0]).toEqual(compiled[1]);
  expect(compiled[0].melody).toEqual(workingScore.melody);
  await expect(page.getByLabel("Current working version")).not.toContainText("有未保存修改");
  // Cancel a long live note using the selector itself, before its scheduled end.
  await page.getByLabel("Editor audition mode").selectOption("melody");
  await page.getByRole("button",{name:"Tab n1 C4 2弦1格",exact:true}).click();
  await page.getByRole("button",{name:"預聽音高",exact:true}).click();
  await page.evaluate(() => { (window as any).__tones.stopped = 0; });
  await connection.selectOption("connected");
  await expect.poll(() => page.evaluate(() => (window as any).__tones.stopped)).toBeGreaterThan(0);
});
