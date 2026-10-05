import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

// Generate with current backend code, without restarting the production server.
let fixtures: { name: string; score: unknown; xml: string }[];
test.beforeAll(() => {
  const project = path.resolve(process.cwd(), "..");
  fixtures = JSON.parse(execFileSync("docker", ["compose", "run", "--rm", "-T", "-v",
    `${project}/backend:/app`, "backend", "sh", "-c",
    "PYTHONPATH=. python scripts/musicxml_reader_fixtures.py"], { cwd: project, encoding: "utf8", timeout: 60000 }));
});

for (const width of [1280, 390]) {
  test(`real exporter draws harmony changes and tied TAB at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const fixture = fixtures.find(f => f.name === "chord-change-under-tie")!;
    await page.route("**/api/v1/jobs/xml-render", r => r.fulfill({ json: {
      id: "xml-render", status: "completed", progress: 100, artifacts: [], score: fixture.score,
    } }));
    await page.route("**/rhythm-patterns?*", r => r.fulfill({ json: [] }));
    await page.route("**/chord-voicings?*", r => r.fulfill({ json: [] }));
    await page.route("**/api/v1/jobs/xml-render/audio", r => r.fulfill({ status: 404, body: "No source in synthetic fixture" }));
    await page.route("**/scores/musicxml", async r => {
      if (process.env.GUITARSCRIBE_LIVE_SMOKE === "1") {
        const response = await page.request.post("http://127.0.0.1:8000/scores/musicxml", { data: r.request().postDataJSON() });
        expect(response.ok()).toBe(true);
        return r.fulfill({ response });
      }
      return r.fulfill({ contentType: "application/xml", body: fixture.xml });
    });
    await page.goto(`${process.env.GUITARSCRIBE_UI_URL ?? ""}/?job=xml-render`);
    await page.getByText("Melody & Tab previews · Experimental", { exact: true }).click();
    const host = page.getByLabel("Standard notation and guitar tab preview", { exact: true });
    await host.scrollIntoViewIfNeeded();
    try { await expect(host.locator("svg").first()).toBeVisible({ timeout: 10000 }); }
    catch (error) { console.log("Preview markup:", await host.innerHTML()); throw error; }
    await expect(host.locator("svg text", { hasText: /^C$/ }).first()).toBeVisible();
    await expect(host.locator("svg text", { hasText: /^G$/ }).first()).toBeVisible();
    await expect(page.locator(".alphatab-error")).toHaveCount(0);
    await expect.poll(() => host.locator(".at-surface").evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThan(150);
    await page.locator(".alphatab-panel").screenshot({ path: testInfo.outputPath(`notation-${width}.png`) });
    const bounds = await host.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1);
  });
}
