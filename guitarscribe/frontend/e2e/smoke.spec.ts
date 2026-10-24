import { expect, test } from "@playwright/test";

test("shows the legal upload workflow", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "選擇來源，開始修譜" })).toBeVisible();
  await expect(page.getByText(/請使用有權分析的來源/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Start analysis" })).toBeVisible();
  await expect(page.getByText("No song loaded yet")).toBeVisible();
});
