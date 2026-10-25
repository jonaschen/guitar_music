import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";

const packetDirectory = path.resolve(process.cwd(), "public/listening/external-checkpoint-2026-10-25");
const packetReady = existsSync(path.join(packetDirectory, "index.html"))
  && existsSync(path.join(packetDirectory, "packet.json"));

test.skip(!packetReady, "External checkpoint packet is not ready yet.");

test("external checkpoint offers two mutually exclusive three-track comparisons", async ({ page }, testInfo) => {
  const base = process.env.GUITARSCRIBE_UI_URL ?? "http://127.0.0.1:4173";
  await page.goto(`${base}/listening/external-checkpoint-2026-10-25/index.html`);
  await expect(page.getByRole("heading", { name: "外部版本比較", exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("試聽清單已載入。");
  await expect(page.getByText("兩版使用相同音色；外部輸出含重疊音與超出原人聲的尾音，均原樣保留。", { exact: true })).toBeVisible();

  const groups = page.locator("main section");
  await expect(groups).toHaveCount(2);
  for (const group of await groups.all()) {
    await expect(group.locator("audio")).toHaveCount(1);
    await expect(group.locator(".tracks button")).toHaveCount(3);
    await expect(group.locator("h2")).not.toHaveText("");
  }

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath("external-checkpoint-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: testInfo.outputPath("external-checkpoint-mobile.png"), fullPage: true });

  const firstGroup = groups.nth(0);
  const secondGroup = groups.nth(1);
  const firstAudio = firstGroup.locator("audio");
  const secondAudio = secondGroup.locator("audio");

  // Dispatch in one browser task to exercise rapid changes before play() settles.
  await page.evaluate(() => {
    const buttons = [...document.querySelectorAll<HTMLButtonElement>(".tracks button")];
    buttons[0].click();
    buttons[1].click();
    buttons[5].click();
  });

  await expect.poll(() => secondAudio.evaluate(audio => !audio.paused && audio.currentTime > 0), {
    timeout: 8000,
  }).toBe(true);
  await expect(firstAudio).toHaveJSProperty("paused", true);
  await expect.poll(() => secondAudio.evaluate(audio => audio.src === audio.dataset.activeSource)).toBe(true);

  await page.getByRole("button", { name: "全部停止", exact: true }).click();
  await expect(firstAudio).toHaveJSProperty("paused", true);
  await expect(secondAudio).toHaveJSProperty("paused", true);
  await expect.poll(() => secondAudio.evaluate(audio => audio.currentTime)).toBe(0);

  await page.route("**/listening/external-checkpoint-2026-10-25/anthem-1.wav", route =>
    route.fulfill({ status: 404, body: "Missing audio fixture" }));
  await firstGroup.locator(".tracks button").nth(2).click();
  await expect(page.getByRole("status")).toContainText("失敗", { timeout: 5000 });
});
