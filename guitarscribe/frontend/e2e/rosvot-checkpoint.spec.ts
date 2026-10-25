import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";

const packetDirectory = path.resolve(process.cwd(), "public/listening/rosvot-checkpoint-2026-10-25");
const packetReady = existsSync(path.join(packetDirectory, "index.html"))
  && existsSync(path.join(packetDirectory, "packet.json"));

test.skip(!packetReady, "ROSVOT checkpoint packet is not ready yet.");

test("ROSVOT checkpoint serves three groups with three mutually exclusive tracks each", async ({ page }, testInfo) => {
  const base = process.env.GUITARSCRIBE_UI_URL ?? "http://127.0.0.1:4173";
  const pageUrl = `${base}/listening/rosvot-checkpoint-2026-10-25/index.html`;
  await page.goto(pageUrl);
  await expect(page.getByRole("heading", { name: "ROSVOT 探索性比較", exact: true })).toBeVisible();
  await expect(page.getByText(/尚未通過完整驗證/)).toBeVisible();
  await expect(page.getByText(/可能漏掉短音或休止/)).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("試聽清單已載入。");

  const groups = page.locator("main section");
  await expect(groups).toHaveCount(3);
  for (const group of await groups.all()) {
    await expect(group.locator("audio")).toHaveCount(1);
    await expect(group.locator(".tracks button")).toHaveCount(3);
    await expect(group.locator("h2")).not.toHaveText("");
    await expect(group.locator("p")).not.toHaveText("");
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath("rosvot-checkpoint-desktop.png"), fullPage: true });

  // Dispatch several track changes in one browser task while play() is pending.
  await page.evaluate(() => {
    const buttons = [...document.querySelectorAll<HTMLButtonElement>(".tracks button")];
    buttons[0].click();
    buttons[1].click();
    buttons[8].click();
  });

  const activeAudio = groups.nth(2).locator("audio");
  await expect.poll(() => activeAudio.evaluate(audio => !audio.paused && audio.currentTime > 0), {
    timeout: 8000,
  }).toBe(true);
  for (let index = 0; index < 2; index++) {
    await expect(groups.nth(index).locator("audio")).toHaveJSProperty("paused", true);
  }

  await page.getByRole("button", { name: "全部停止", exact: true }).click();
  for (const group of await groups.all()) await expect(group.locator("audio")).toHaveJSProperty("paused", true);

  const missingFile = await groups.nth(0).locator(".tracks button").nth(2).getAttribute("data-source-file");
  expect(missingFile).toBeTruthy();
  const missingUrl = new URL(missingFile!, pageUrl);
  await page.route(url => new URL(url).pathname === missingUrl.pathname, route =>
    route.fulfill({ status: 404, body: "Missing ROSVOT model fixture" }));
  await groups.nth(0).locator(".tracks button").nth(2).click();
  await expect(page.getByRole("status")).toContainText("失敗", { timeout: 5000 });
});
