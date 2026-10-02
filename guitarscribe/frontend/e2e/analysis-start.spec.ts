import { expect, test } from "@playwright/test";

for (const source of ["upload", "youtube"]) {
  test(`submits pre-analysis skip for ${source}`, async ({ page }) => {
    let submitted = false;
    await page.route(source === "upload" ? "**/api/v1/jobs" : "**/api/v1/youtube-jobs", async (route) => {
      if (source === "upload") {
        const body = route.request().postData()!;
        expect(body).toContain('name="skip_seconds"\r\n\r\n19');
      } else expect(route.request().postDataJSON().skip_seconds).toBe(19);
      submitted = true;
      await route.fulfill({ json: { id: "skipped", status: "queued", progress: 0, artifacts: [], message: "Queued" } });
    });
    await page.route("**/api/v1/jobs/skipped", (route) => route.fulfill({ json: { id: "skipped", status: "queued", progress: 0, artifacts: [], message: "Queued" } }));
    await page.goto("/");
    await expect(page.getByLabel("Skip opening seconds")).toHaveValue("0");
    if (source === "upload") await page.locator('input[type="file"]').setInputFiles({ name: "mv.wav", mimeType: "audio/wav", buffer: Buffer.from("test") });
    else await page.getByLabel("YouTube video URL").fill("https://www.youtube.com/watch?v=example");
    await page.getByLabel("Skip opening seconds").fill("19");
    await page.getByRole("button", { name: "Start analysis", exact: true }).click();
    await expect.poll(() => submitted).toBe(true);
  });
}

test("rejects negative skip before sending an upload", async ({ page }) => {
  let submitted = false;
  await page.route("**/api/v1/jobs", (route) => { submitted = true; return route.abort(); });
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles({ name: "mv.wav", mimeType: "audio/wav", buffer: Buffer.from("test") });
  await page.getByLabel("Skip opening seconds").fill("-1");
  await page.getByRole("button", { name: "Start analysis", exact: true }).click();
  expect(await page.getByLabel("Skip opening seconds").evaluate((input: HTMLInputElement) => input.validity.valid)).toBe(false);
  expect(submitted).toBe(false);
});
