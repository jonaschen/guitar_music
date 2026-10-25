import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";

const packetDirectory = path.resolve(process.cwd(), "public/listening/third-source-2026-10-25");
const packetReady = existsSync(path.join(packetDirectory, "index.html"))
  && existsSync(path.join(packetDirectory, "packet.json"));

test.skip(!packetReady, "Third-source checkpoint packet is not ready yet.");

test("third-source checkpoint plays original, vocal stem and G melody in both groups", async ({ page }, testInfo) => {
  const base = process.env.GUITARSCRIBE_UI_URL ?? "http://127.0.0.1:4173";
  await page.goto(`${base}/listening/third-source-2026-10-25/index.html`);
  await expect(page.getByRole("heading", { name: "第三來源旋律檢查", exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("試聽清單已載入。");

  const groups = page.locator("main section");
  const count = await groups.count();
  expect(count).toBe(2);
  for (const group of await groups.all()) {
    await expect(group.locator("audio")).toHaveCount(1);
    const buttons = group.locator(".tracks button");
    await expect(buttons).toHaveCount(3);
    const labels = await buttons.allTextContents();
    expect(labels.map(label => label.replace(/\s+/g, ""))).toEqual(["播放：原曲", "播放：分離人聲", "播放：G旋律"]);
  }

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath("third-source-checkpoint-desktop.png"), fullPage: true });

  await page.evaluate(() => {
    const buttons = [...document.querySelectorAll<HTMLButtonElement>(".tracks button")];
    buttons[0].click();
    buttons[1].click();
    buttons[buttons.length - 1].click();
  });

  const activeAudio = groups.nth(count - 1).locator("audio");
  await expect.poll(() => activeAudio.evaluate(audio => !audio.paused && audio.currentTime > 0), {
    timeout: 8000,
  }).toBe(true);
  for (let index = 0; index < count - 1; index++) {
    await expect(groups.nth(index).locator("audio")).toHaveJSProperty("paused", true);
  }

  await page.getByRole("button", { name: "全部停止", exact: true }).click();
  for (const group of await groups.all()) await expect(group.locator("audio")).toHaveJSProperty("paused", true);

  await page.route("**/listening/third-source-2026-10-25/g-1.wav", route =>
    route.fulfill({ status: 404, body: "Missing G melody fixture" }));
  await groups.nth(0).locator(".tracks button").nth(2).click();
  await expect(page.getByRole("status")).toContainText("失敗", { timeout: 5000 });
});
