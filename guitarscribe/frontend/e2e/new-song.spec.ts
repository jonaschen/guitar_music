import { test, expect, type Page } from "@playwright/test";

const score = {
  schema_version: "1.0", song: { title: "Existing song", source_type: "local", duration_seconds: 8 },
  analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: .5, warnings: [] },
  key_context: { source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" }, shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" }, transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true },
  guitar: { tuning: [40,45,50,55,59,64], tuning_name: "EADGBE", max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner", tab_preference: "balanced" },
  beats: Array.from({length: 16}, (_, i) => ({time: i*.5, beat: i%4+1, measure: Math.floor(i/4)+1})),
  chords: [], melody: [{id:"n",start:0,end:.5,midi:60,note:"C4",string:2,fret:1}],
  rhythm: {subdivision:8,pattern_id:"",display:[],confidence:0},
  provenance: {beat_engine:"test",chord_engine:"test",melody_engine:"test",parameters:{candidate_source_job_id:"old"}},
};
async function setup(page: Page, melody = true, separation = false) {
  await page.addInitScript(() => localStorage.removeItem("guitarscribe.workspaceMode"));
  await page.route("**/api/v1/capabilities", r => r.fulfill({json:{youtube_enabled:true,vocal_separation_enabled:separation,improved_accompaniment:true,melody_available:melody,beat_engine:"beat_this",chord_engine:"chordino"}}));
  await page.route("**/api/v1/jobs/old", r => r.fulfill({json:{id:"old",status:"completed",progress:100,score,artifacts:[]}}));
  await page.route("**/rhythm-patterns?*", r => r.fulfill({json:[]}));
  await page.goto("/?job=old");
  await expect(page.getByRole("button",{name:"分析新曲目",exact:true})).toBeVisible();
}

test("new source preserves the current audio and unapplied draft; failed upload keeps work", async ({page}) => {
  await setup(page, false);
  const audio = await page.locator("audio").last().getAttribute("src");
  await page.getByRole("button",{name:"Tab n C4 2弦1格",exact:true}).click();
  await page.getByLabel("Tab fret",{exact:true}).fill("3");
  await page.getByRole("button",{name:"分析新曲目",exact:true}).click();
  await expect(page.getByLabel("Analysis duration")).toHaveValue("45");
  await expect(page.getByText("目前僅分析拍點與和弦，不會產生旋律；完成後可手動補音。",{exact:true})).toBeVisible();
  await page.locator('input[type="file"]').first().setInputFiles({name:"new.wav",mimeType:"audio/wav",buffer:Buffer.from("sample")});
  expect(await page.locator("audio").last().getAttribute("src")).toBe(audio);
  await expect(page.getByLabel("Tab fret",{exact:true})).toHaveValue("3");
  await page.route("**/api/v1/jobs", r => {
    const body = r.request().postData()!;
    expect(body).toContain('name="analysis_seconds"\r\n\r\n45');
    expect(body).toContain('name="chord_complexity"\r\n\r\nfull');
    return r.fulfill({status:503,body:"offline"});
  });
  await page.getByRole("button",{name:"Start analysis",exact:true}).click();
  await expect(page.locator(".error-banner")).toContainText("offline");
  await expect(page.getByRole("heading",{name:"Existing song",exact:true})).toBeVisible();
  await expect(page.getByLabel("Tab fret",{exact:true})).toHaveValue("3");
});

test("dirty submission can be cancelled; successful YouTube analysis opens focus", async ({page}) => {
  await setup(page);
  await page.route("**/scores/melody/edit", r => {
    const updated = structuredClone(r.request().postDataJSON().score);
    updated.melody[0].fret=3; updated.melody[0].midi=62;
    return r.fulfill({json:{score:updated,selected_note_id:"n"}});
  });
  await page.getByRole("button",{name:"Tab n C4 2弦1格",exact:true}).click();
  await page.getByLabel("Tab fret",{exact:true}).fill("3");
  await page.getByRole("button",{name:"Apply note",exact:true}).click();
  await expect(page.getByLabel("Current working version")).toContainText("有未保存修改");
  await page.getByRole("button",{name:"分析新曲目",exact:true}).click();
  await page.getByLabel("YouTube video URL").fill("https://www.youtube.com/watch?v=example");
  let requests=0;
  await page.route("**/api/v1/youtube-jobs", r => {
    requests++;
    expect(r.request().postDataJSON()).toMatchObject({analysis_seconds:45,chord_complexity:"full"});
    return r.fulfill({json:{id:"new",status:"queued",progress:0}});
  });
  await page.route("**/api/v1/jobs/new", r => r.fulfill({json:{id:"new",status:"completed",progress:100,score:{...score,song:{...score.song,title:"New song"},provenance:{...score.provenance,parameters:{candidate_source_job_id:"new"}}}}}));
  page.once("dialog", d => d.dismiss());
  await page.getByRole("button",{name:"Start analysis",exact:true}).click();
  expect(requests).toBe(0);
  page.once("dialog", d => d.accept());
  await page.getByRole("button",{name:"Start analysis",exact:true}).click();
  await expect(page.getByRole("heading",{name:"New song",exact:true})).toBeVisible();
  await expect(page.getByLabel("新曲目來源")).toBeHidden();
  await expect(page.locator(".melody-editor")).toHaveCount(1);
});

test("edits made while a new analysis runs require explicit result confirmation", async ({page}) => {
  await setup(page);
  let complete = false;
  await page.route("**/api/v1/youtube-jobs", r => r.fulfill({json:{id:"new",status:"queued",progress:0}}));
  await page.route("**/api/v1/jobs/new", r => r.fulfill({json:complete
    ? {id:"new",status:"completed",progress:100,score:{...score,song:{...score.song,title:"New song"},provenance:{...score.provenance,parameters:{candidate_source_job_id:"new"}}}}
    : {id:"new",status:"processing",progress:50}}));
  await page.route("**/scores/melody/edit", r => {
    const updated = structuredClone(r.request().postDataJSON().score);
    updated.melody[0].fret=3;
    return r.fulfill({json:{score:updated,selected_note_id:"n"}});
  });
  await page.getByRole("button",{name:"分析新曲目",exact:true}).click();
  await page.getByLabel("YouTube video URL").fill("https://www.youtube.com/watch?v=example");
  await page.getByRole("button",{name:"Start analysis",exact:true}).click();
  await expect(page.locator(".job-progress progress")).toHaveAttribute("value", "50");
  await page.getByRole("button",{name:"Tab n C4 2弦1格",exact:true}).click();
  await page.getByLabel("Tab fret",{exact:true}).fill("3");
  await page.getByRole("button",{name:"Apply note",exact:true}).click();
  await expect(page.getByLabel("Current working version")).toContainText("有未保存修改");
  complete = true;
  await expect(page.getByLabel("工作版本", {exact:true}).getByText(/新曲目已完成；目前工作譜在分析期間改變/)).toBeVisible();
  await expect(page.getByRole("heading",{name:"Existing song",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"確認恢復版本（可 Undo）",exact:true}).click();
  await expect(page.getByRole("heading",{name:"New song",exact:true})).toBeVisible();
  await expect(page).toHaveURL(/job=new/);
});

test("vocal input defaults to available separation and focus offers explicit two-stage G", async ({page}) => {
  await setup(page, true, true);
  await expect(page.getByText(/目前為原分析／其他音符版本，尚未套用 G/)).toBeVisible();
  const g = structuredClone(score);
  g.provenance.parameters = {...g.provenance.parameters, melody_note_processing:"bounded-source-v1"} as typeof g.provenance.parameters;
  g.melody[0].midi = 62;
  await page.route("**/api/v1/jobs/old/melody-candidate", r => r.fulfill({json:g}));
  await page.getByText("Contour → 可編輯音符候選（G，實驗性）", {exact:true}).click();
  await page.getByRole("button",{name:"產生 Contour 音符候選",exact:true}).click();
  await expect(page.getByRole("button",{name:"套用候選到工作譜（可 Undo）",exact:true})).toBeVisible();
  await expect(page.getByLabel("Current working version")).not.toContainText("Contour G 候選");
  await page.getByRole("button",{name:"套用候選到工作譜（可 Undo）",exact:true}).click();
  await expect(page.getByLabel("Current working version")).toContainText("Contour G 候選");
  await page.getByRole("button",{name:"分析新曲目",exact:true}).click();
  await page.getByText("進階分析設定",{exact:true}).click();
  await expect(page.locator(".vocal-isolation-option input")).toBeChecked();
  await page.getByLabel("YouTube video URL").fill("https://www.youtube.com/watch?v=example");
  let separated = false;
  await page.route("**/api/v1/youtube-jobs", r => {
    separated = r.request().postDataJSON().separate_vocals;
    return r.fulfill({status:503,body:"test stop"});
  });
  page.once("dialog", d => d.accept());
  await page.getByRole("button",{name:"Start analysis",exact:true}).click();
  await expect.poll(() => separated).toBe(true);
});

for (const terminal of ["failed", "cancelled"]) {
  test(`${terminal} new analysis preserves the prior score and permits retry`, async ({page}) => {
    await setup(page);
    await page.route("**/api/v1/youtube-jobs", r => r.fulfill({json:{id:"terminal",status:"queued",progress:0}}));
    await page.route("**/api/v1/jobs/terminal", r => r.fulfill({json:{id:"terminal",status:terminal,progress:0,message:"Analysis ended"}}));
    await page.getByRole("button",{name:"分析新曲目",exact:true}).click();
    await page.getByLabel("YouTube video URL").fill("https://www.youtube.com/watch?v=example");
    await page.getByRole("button",{name:"Start analysis",exact:true}).click();
    await expect(page.locator(".error-banner")).toContainText("Analysis ended");
    await expect(page.getByRole("heading",{name:"Existing song",exact:true})).toBeVisible();
    await expect(page.getByRole("button",{name:"Start analysis",exact:true})).toBeEnabled();
    await expect(page.getByRole("button",{name:"確認恢復版本（可 Undo）",exact:true})).toHaveCount(0);
    await expect(page.getByRole("button",{name:"Tab n C4 2弦1格",exact:true})).toBeVisible();
    await expect(page).toHaveURL(/job=old/);
    await expect(page.getByRole('region',{name:'和弦核對'}).getByRole('button',{name:'從這段開頭播放'})).toBeEnabled();
    await page.reload();
    await expect(page.getByRole("heading",{name:"Existing song",exact:true})).toBeVisible();
  });
}


test('failed replacement restores a saved revision link and keeps edits made during analysis', async ({page}) => {
  await setup(page);
  await page.route('**/revisions/saved-old', r=>r.fulfill({json:score}));
  await page.goto('/?revision=saved-old&view=accompaniment');
  let failed=false;
  await page.route('**/api/v1/youtube-jobs', r=>r.fulfill({json:{id:'replacement',status:'queued',progress:0}}));
  await page.route('**/api/v1/jobs/replacement', r=>r.fulfill({json:{id:'replacement',status:failed?'failed':'processing',progress:50,message:'Analysis ended'}}));
  await page.getByRole('button',{name:'分析新曲目',exact:true}).click();
  await page.getByLabel('YouTube video URL').fill('https://www.youtube.com/watch?v=example');
  await page.getByRole('button',{name:'Start analysis',exact:true}).click();
  await expect(page.locator('.job-progress progress')).toHaveAttribute('value','50');
  await page.getByRole('button',{name:'顯示完整工具',exact:true}).click();
  await page.getByRole('combobox',{name:'Max capo',exact:true}).selectOption('7');
  failed=true;
  await expect(page.locator('.error-banner')).toContainText('Analysis ended');
  await expect(page).toHaveURL(/revision=saved-old/);
  await expect(page.getByRole('combobox',{name:'Max capo',exact:true})).toHaveValue('7');
  await expect(page.getByLabel('Current working version')).toContainText('有未保存修改');
  await page.getByRole('button',{name:'Undo',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'Max capo',exact:true})).toHaveValue('8');
  await page.reload();
  await expect(page.getByRole('heading',{name:'Existing song',exact:true})).toBeVisible();
  await expect(page.getByLabel('Current working version')).toContainText('已保存／載入');
});

test('cancel button restores the prior source and releases the new-analysis form', async ({page}) => {
  await setup(page);
  await page.route('**/api/v1/youtube-jobs', r=>r.fulfill({json:{id:'running',status:'queued',progress:0}}));
  await page.route('**/api/v1/jobs/running', r=>r.fulfill({json:{id:'running',status:'processing',progress:50}}));
  await page.route('**/api/v1/jobs/running/cancel', r=>r.fulfill({json:{id:'running',status:'cancelled',progress:50,message:'Cancelled'}}));
  await page.getByRole('button',{name:'分析新曲目',exact:true}).click();
  await page.getByLabel('YouTube video URL').fill('https://www.youtube.com/watch?v=example');
  await page.getByRole('button',{name:'Start analysis',exact:true}).click();
  await expect(page.locator('.job-progress progress')).toHaveAttribute('value','50');
  await page.getByRole('button',{name:'Cancel analysis',exact:true}).click();
  await expect(page).toHaveURL(/job=old/);
  await expect(page.getByRole('button',{name:'Start analysis',exact:true})).toBeEnabled();
  await expect(page.getByRole('region',{name:'和弦核對'}).getByRole('button',{name:'從這段開頭播放'})).toBeEnabled();
  await expect(page.getByRole('heading',{name:'Existing song',exact:true})).toBeVisible();
  await expect(page.locator('.job-progress')).toHaveCount(0);
});
