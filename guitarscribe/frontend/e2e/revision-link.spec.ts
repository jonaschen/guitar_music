import { expect, test, type Page, type Route } from "@playwright/test";
import type { SongScore } from "../src/types";

function makeScore(midi: number, version: "original" | "g", sourceJob?: string): SongScore {
  const note = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"][midi % 12];
  const score: SongScore = {
    schema_version: "1.0",
    song: { title: version === "original" ? "Original 553 analysis" : "Saved G revision", source_type: "local", duration_seconds: 8 },
    analysis: { key: "C", mode: "major", bpm: 120, time_signature: "4/4", capo: 0, confidence: .5, warnings: [] },
    key_context: {
      source: { key: "C", mode: "major" }, target: { key: "C", mode: "major" },
      shape: { key: "C", mode: "major" }, sounding: { key: "C", mode: "major" },
      transpose_semitones: 0, accidental_preference: "auto", audio_matches_notation: true,
    },
    guitar: { tuning: [40, 45, 50, 55, 59, 64], tuning_name: "EADGBE", capo: 0, max_capo: 8, max_fret: 15, handedness: "right", difficulty: "beginner", tab_preference: "balanced" },
    beats: Array.from({ length: 16 }, (_, i) => ({ time: i * .5, beat: i % 4 + 1, measure: Math.floor(i / 4) + 1, confidence: 1 })),
    chords: [],
    melody: [{ id: "n1", start: 0, end: .5, midi, note: `${note}${Math.floor(midi / 12) - 1}`, confidence: .5, string: 2, fret: Math.max(0, midi - 59), origin: "model", edited: false }],
    rhythm: { subdivision: 8, pattern_id: "", display: [], confidence: 0, label: "" },
    provenance: {
      beat_engine: "test", chord_engine: "test", melody_engine: "test",
      parameters: version === "g"
        ? { melody_note_processing: "bounded-source-v1", ...(sourceJob ? { candidate_source_job_id: sourceJob } : {}) }
        : { melody_note_processing: "source-timed-semitone-v2" },
    },
  };
  return score;
}

const originalScore = makeScore(60, "original");
const gScore = makeScore(64, "g", "analysis-job");
const alternateGScore = makeScore(62, "g");

async function seedStorage(page: Page, activeJobId: string, revisionId?: string) {
  await page.addInitScript(({ active, revision }) => {
    localStorage.setItem("guitarscribe.activeJobId", active);
    if (revision) {
      localStorage.setItem(`guitarscribe.melodyRevision.${active}`, revision);
      localStorage.setItem("guitarscribe.savedVersion", JSON.stringify({
        id: revision, label: "Contour G 候選 · 1 音符", jobId: active,
      }));
    }
  }, { active: activeJobId, revision: revisionId });
}

async function mockJobs(page: Page, requests: string[] = []) {
  await page.route("**/api/v1/jobs/**", route => {
    const id = new URL(route.request().url()).pathname.split("/").at(-1)!;
    requests.push(id);
    const score = id === "analysis-job" ? originalScore : undefined;
    if (!score) return route.fulfill({ status: 404, json: { detail: `Unknown job ${id}` } });
    return route.fulfill({ json: { id, status: "completed", progress: 100, artifacts: [], score } });
  });
  await page.route("**/rhythm-patterns?*", route => route.fulfill({ json: [] }));
}

async function mockRevision(page: Page, id: string, score: SongScore) {
  await page.route(`**/revisions/${id}`, route => route.fulfill({ json: score }));
}

test("revision deep link wins over job query and activeJobId", async ({ page }) => {
  const jobRequests: string[] = [];
  await seedStorage(page, "stored-job");
  await mockJobs(page, jobRequests);
  await mockRevision(page, "g-link", makeScore(64, "g"));

  await page.goto("/?revision=g-link&job=url-job");

  await expect(page.getByLabel("Current working version")).toContainText("Contour G 候選");
  await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：g-link");
  await expect(page.getByRole("heading", { name: "Saved G revision" })).toBeVisible();
  expect(jobRequests).not.toContain("url-job");
  expect(jobRequests).not.toContain("stored-job");
});

test("confirmed restore and successful save update revision URL; refresh loads that saved score", async ({ page }) => {
  await seedStorage(page, "analysis-job", "g-link");
  await mockJobs(page);
  await mockRevision(page, "g-link", gScore);
  let latestSaved: SongScore = gScore;
  await page.route("**/revisions", route => {
    if (route.request().method() !== "POST") return route.fallback();
    latestSaved = route.request().postDataJSON().score as SongScore;
    return route.fulfill({ json: { revision_id: "g-saved" } });
  });
  await mockRevision(page, "g-saved", latestSaved);

  await page.goto("/?job=analysis-job");
  await expect(page.getByLabel("Current working version")).toContainText("原分析音符");
  await page.getByRole("button", { name: "恢復上次保存版本", exact: true }).click();
  await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
  await expect.poll(() => new URL(page.url()).searchParams.get("revision")).toBe("g-link");
  await expect(new URL(page.url()).searchParams.has("job")).toBe(false);

  await page.getByRole("button", { name: "保存目前工作版本", exact: true }).click();
  await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：g-saved");
  await expect.poll(() => new URL(page.url()).searchParams.get("revision")).toBe("g-saved");

  await page.reload();
  await expect(page.getByLabel("Current working version")).toContainText("Contour G 候選");
  await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：g-saved");
  await expect(page.getByRole("heading", { name: "Saved G revision" })).toBeVisible();
});

test("missing revision deep link reports the error without falling back to the original job", async ({ page }) => {
  const jobRequests: string[] = [];
  await seedStorage(page, "stored-job");
  await mockJobs(page, jobRequests);
  await page.route("**/revisions/missing", route => route.fulfill({ status: 404, json: { detail: "Revision not found" } }));

  await page.goto("/?revision=missing&job=analysis-job");

  await expect(page.locator(".error-banner")).toContainText("未改播原分析");
  await expect(page.getByLabel("Current working version")).toContainText("尚未載入樂譜");
  await expect(page.getByRole("heading", { name: "Original 553 analysis" })).toHaveCount(0);
  expect(jobRequests).toEqual([]);
});

test("a late deep-link response cannot replace a different revision restored by the user", async ({ page }) => {
  let slowResponse: Route | undefined;
  await mockJobs(page);
  await page.route("**/revisions/slow-link", route => { slowResponse = route; });
  await mockRevision(page, "manual-g", alternateGScore);

  await page.goto("/?revision=slow-link&job=analysis-job");
  await expect.poll(() => Boolean(slowResponse)).toBe(true);
  await page.getByRole("button", { name: "取消讀取版本", exact: true }).click();
  await page.getByLabel("Saved revision ID").fill("manual-g");
  await page.getByRole("button", { name: "載入已保存修訂", exact: true }).click();
  await page.getByRole("button", { name: "確認恢復版本（可 Undo）", exact: true }).click();
  await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：manual-g");
  await expect.poll(() => new URL(page.url()).searchParams.get("revision")).toBe("manual-g");
  await page.getByText("旋律人工編輯 · Melody editor", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Tab n1 D4 2弦3格", exact: true })).toBeVisible();

  await slowResponse!.fulfill({ json: gScore });
  await expect(page.getByLabel("Current working version")).toContainText("已保存／載入：manual-g");
  await expect(page.getByRole("button", { name: "Tab n1 D4 2弦3格", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Tab n1 E4 2弦5格", exact: true })).toHaveCount(0);
});

test("starting a new analysis clears the revision deep link", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("guitarscribe.workspaceMode", "focus"));
  await mockJobs(page);
  await mockRevision(page, "g-link", makeScore(64, "g"));
  await page.route("**/api/v1/jobs", route => route.fulfill({ json: {
    id: "new-analysis", status: "queued", progress: 0, artifacts: [], message: "Queued",
  } }));
  await page.route("**/api/v1/jobs/new-analysis", route => route.fulfill({ json: {
    id: "new-analysis", status: "queued", progress: 0, artifacts: [], message: "Queued",
  } }));

  await page.goto("/?revision=g-link");
  await expect(page.getByLabel("Current working version")).toContainText("Contour G 候選");
  await page.getByRole("button", { name: "顯示完整工具", exact: true }).click();
  await page.locator('input[type="file"][accept*=".wav"]').setInputFiles({ name: "new-song.wav", mimeType: "audio/wav", buffer: Buffer.from("audio") });
  await page.getByRole("button", { name: "Start analysis", exact: true }).click();

  await expect.poll(() => new URL(page.url()).searchParams.get("job")).toBe("new-analysis");
  await expect(new URL(page.url()).searchParams.has("revision")).toBe(false);
});

test("submitting a new analysis invalidates a pending startup revision before job creation resolves", async ({ page }) => {
  let slowRevision: Route | undefined;
  let createJob: Route | undefined;
  await page.route("**/revisions/slow-startup", route => { slowRevision = route; });
  await page.route("**/api/v1/jobs", route => {
    if (route.request().method() === "POST") { createJob = route; return; }
    return route.fallback();
  });
  await page.route("**/api/v1/jobs/new-analysis", route => route.fulfill({ json: {
    id: "new-analysis", status: "queued", progress: 0, artifacts: [], message: "Queued",
  } }));

  await page.goto("/?revision=slow-startup");
  await expect.poll(() => Boolean(slowRevision)).toBe(true);
  await page.locator('input[type="file"][accept*=".wav"]').setInputFiles({ name: "new-song.wav", mimeType: "audio/wav", buffer: Buffer.from("audio") });
  const createRequest = page.waitForRequest(request => new URL(request.url()).pathname === "/api/v1/jobs" && request.method() === "POST");
  await page.getByRole("button", { name: "Start analysis", exact: true }).click();
  await createRequest;
  await expect.poll(() => Boolean(createJob)).toBe(true);

  const slowResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/revisions/slow-startup");
  await slowRevision!.fulfill({ json: makeScore(64, "g") });
  await slowResponse;
  await expect(page.getByRole("heading", { name: "No song loaded yet" })).toBeVisible();
  await expect(page.getByLabel("Current working version")).toContainText("尚未載入樂譜");

  await createJob!.fulfill({ json: { id: "new-analysis", status: "queued", progress: 0, artifacts: [], message: "Queued" } });
  await expect.poll(() => new URL(page.url()).searchParams.get("job")).toBe("new-analysis");
  await expect(new URL(page.url()).searchParams.has("revision")).toBe(false);
});

test("an older save response cannot replace the URL after a new analysis starts", async ({ page }) => {
  let oldSave: Route | undefined;
  let createJob: Route | undefined;
  await page.addInitScript(() => localStorage.setItem("guitarscribe.workspaceMode", "focus"));
  await mockJobs(page);
  await page.route("**/revisions", route => {
    if (route.request().method() === "POST") { oldSave = route; return; }
    return route.fallback();
  });
  await page.route("**/api/v1/jobs", route => {
    if (route.request().method() === "POST") { createJob = route; return; }
    return route.fallback();
  });
  await page.route("**/api/v1/jobs/new-job", route => route.fulfill({ json: {
    id: "new-job", status: "queued", progress: 0, artifacts: [], message: "Queued",
  } }));

  await page.goto("/?job=analysis-job");
  await expect(page.getByLabel("Current working version")).toContainText("原分析音符");
  await page.getByRole("button", { name: "顯示完整工具", exact: true }).click();
  const saveRequest = page.waitForRequest(request => new URL(request.url()).pathname === "/revisions" && request.method() === "POST");
  await page.getByRole("button", { name: "保存目前工作版本", exact: true }).click();
  await saveRequest;
  await expect.poll(() => Boolean(oldSave)).toBe(true);

  await page.locator('input[type="file"][accept*=".wav"]').setInputFiles({ name: "new-song.wav", mimeType: "audio/wav", buffer: Buffer.from("audio") });
  const createRequest = page.waitForRequest(request => new URL(request.url()).pathname === "/api/v1/jobs" && request.method() === "POST");
  await page.getByRole("button", { name: "Start analysis", exact: true }).click();
  await createRequest;
  await expect.poll(() => Boolean(createJob)).toBe(true);
  await createJob!.fulfill({ json: { id: "new-job", status: "queued", progress: 0, artifacts: [], message: "Queued" } });
  await expect.poll(() => new URL(page.url()).searchParams.get("job")).toBe("new-job");
  await expect(new URL(page.url()).searchParams.has("revision")).toBe(false);

  const saveResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/revisions");
  await oldSave!.fulfill({ json: { revision_id: "stale-save" } });
  await saveResponse;
  await expect.poll(() => new URL(page.url()).searchParams.get("job")).toBe("new-job");
  await expect(new URL(page.url()).searchParams.has("revision")).toBe(false);
});
