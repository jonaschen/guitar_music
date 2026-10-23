// Run only against a separate service whose --receipts points to a temporary directory.
import { chromium, expect } from '@playwright/test';
const url = process.env.ANCHOR_TEST_URL || 'http://127.0.0.1:8002/';
if (new URL(url).port !== '8002') throw new Error('Use the isolated test service on port 8002');
expect.configure({timeout: 15000});
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true,
  args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'] });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(url);
  try { await expect(page.locator('#skip')).toBeEnabled({timeout:15000}); } catch (e) { console.error(await page.locator('body').innerText(), errors); throw e; }
  await expect(page.locator('#mark')).toBeDisabled();
  await page.keyboard.press('Space');
  await expect(page.locator('#observations li')).toHaveCount(0);
  await page.locator('#skip').click();
  await expect(page.locator('#submit')).toBeDisabled();
  await page.locator('#undo').click();
  await page.locator('#audio').evaluate(async audio => { await audio.play(); });
  await expect(page.locator('#mark')).toBeEnabled();
  await page.keyboard.press('Space');
  await expect(page.locator('#observations li')).toHaveCount(1);
  await page.locator('#audio').evaluate(audio => audio.pause());
  await expect(page.locator('#mark')).toBeDisabled();
  const draft = () => page.evaluate(() => JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('lyric-anchor-capture:')))));
  const original = (await draft()).observations[0];
  await page.getByRole('button', {name: '+0.05 秒調整第 1 項修訂時間', exact: true}).click();
  let adjusted = (await draft()).observations[0];
  expect(adjusted.raw_seconds).toBe(original.raw_seconds);
  expect(adjusted.seconds).toBeCloseTo(original.seconds + .05, 7);
  await page.reload();
  await expect(page.locator('#observations li')).toHaveCount(1);
  expect((await draft()).observations[0]).toEqual(adjusted);
  await page.getByRole('button', {name: '重聽第 1 項標記附近', exact: true}).click();
  await expect.poll(() => page.locator('#audio').evaluate(a => a.paused)).toBe(true);
  const position = await page.locator('#audio').evaluate(a => a.currentTime);
  expect(position).toBeCloseTo(adjusted.seconds + 1, 2);
  await page.locator('#observations input[type=checkbox]').check();
  await page.locator('#skip').click();
  let payload;
  await page.route('**/marks', async route => {
    payload = route.request().postDataJSON();
    await route.fulfill({status: 503, body: 'simulated unavailable'});
  });
  await page.locator('#submit').click();
  await expect(page.locator('#status')).toContainText('提交失敗');
  await expect(page.locator('#submit')).toBeEnabled();
  expect((await draft()).observations).toHaveLength(2);
  await page.unroute('**/marks');
  const response = page.waitForResponse(r => r.url().endsWith('/marks') && r.status() === 200);
  await page.locator('#submit').click();
  const receipt = await (await response).json();
  await expect(page.locator('#receipt')).toContainText(receipt.receipt_id);
  expect(payload.observations[0].raw_seconds).toBe(original.raw_seconds);
  expect(payload.observations[0].reviewed).toBe(true);
  expect(payload.observations[1].skipped).toBe(true);
  expect(await draft()).toBeNull();
  expect(errors).toEqual([]);
  console.log(JSON.stringify({passed:true, receipt_id:receipt.receipt_id,
    checks:['paused guard','space marks once','skip and undo','raw time preserved','draft reload',
      'preview stop','partial submission','failed submission retry','receipt saved','no browser errors']}));
} finally { await browser.close(); }
