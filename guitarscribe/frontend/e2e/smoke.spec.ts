import { expect, test } from "@playwright/test";

test("shows the legal upload workflow", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "把歌曲變成和弦譜" })).toBeVisible();
  await expect(page.getByText(/請使用有權分析的來源/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Start analysis" })).toBeVisible();
  await expect(page.getByText("先選擇音檔或貼上 YouTube 網址，完成分析後會顯示和弦核對頁。", { exact: true })).toBeVisible();
});
