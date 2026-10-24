// Explicit engineering smoke: creates an independent revision of a completed job.
// Usage: node scripts/smoke-new-song.mjs JOB_ID OUTPUT_DIRECTORY
import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const [jobId, output] = process.argv.slice(2);
if (!jobId || !output) throw Error('Provide a completed vocal job ID and output directory');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:5173/?job=${encodeURIComponent(jobId)}`);
  await expect(page.getByLabel('Editor melody version')).toContainText('原分析', { timeout: 30000 });
  await page.getByRole('button', { name: '對照來源片段', exact: true }).click();
  await expect(page.getByLabel('Editor playback status')).toContainText('播放來源音訊', { timeout: 15000 });
  await page.getByRole('button', { name: '暫停，保留位置', exact: true }).click();
  await page.getByText('Contour → 可編輯音符候選（G，實驗性）', { exact: true }).click();
  await page.getByRole('button', { name: '產生 Contour 音符候選', exact: true }).click();
  await expect(page.getByRole('button', { name: '套用候選到工作譜（可 Undo）', exact: true })).toBeVisible({ timeout: 30000 });
  await page.getByRole('button', { name: '套用候選到工作譜（可 Undo）', exact: true }).click();
  await expect(page.getByLabel('Editor melody version')).toContainText('Contour G 候選');
  await page.getByLabel('Editor audition mode').selectOption('ensemble');
  await page.getByRole('button', { name: '重播所選小節', exact: true }).click();
  await expect(page.getByLabel('Editor playback status')).toContainText('播放工作譜', { timeout: 15000 });
  await page.getByRole('button', { name: '暫停，保留位置', exact: true }).click();
  await page.getByText('以版本 ID 保存／載入', { exact: true }).click();
  const saveResponse = page.waitForResponse(r => r.url().endsWith('/revisions') && r.request().method() === 'POST');
  await page.locator('.melody-editor').getByRole('button', { name: 'Save new revision', exact: true }).click();
  const response = await saveResponse;
  expect(response.ok()).toBeTruthy();
  const { revision_id: revisionId } = await response.json();
  const saved = await page.request.get(`http://127.0.0.1:8000/revisions/${revisionId}`);
  const score = await saved.json();
  expect(score).toEqual(response.request().postDataJSON().score);
  expect(score.provenance.parameters.melody_note_processing).toBe('bounded-source-v1');
  const manifestResponse = await page.request.post('http://127.0.0.1:8000/scores/playback/manifest', { data: score });
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json();
  expect(manifest.events.some(event => event.track === 'guitar')).toBeTruthy();
  expect(manifest.events.some(event => event.track === 'melody')).toBeTruthy();
  await page.goto(`http://127.0.0.1:5173/?revision=${revisionId}`);
  await expect(page.getByLabel('Editor melody version')).toContainText('Contour G 候選', { timeout: 30000 });
  await page.screenshot({ path: path.join(output, 'new-song-desktop.png'), fullPage: true });
  expect(errors).toEqual([]);
  await writeFile(path.join(output, 'live-ui-smoke.json'), JSON.stringify({ jobId, revisionId, notes: score.melody.length, events: manifest.events.length, errors, sourceStarted: true, candidateApplied: true, ensembleStarted: true, independentSaveAndReload: true }, null, 2));
  console.log(JSON.stringify({ revisionId, notes: score.melody.length, events: manifest.events.length }));
} finally {
  await browser.close();
}
