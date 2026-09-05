import { expect, test } from "@playwright/test";

test("shows the legal upload workflow", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Paste less. Listen once. Get a playable draft." })).toBeVisible();
  await expect(page.getByText("Rights check")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start analysis" })).toBeVisible();
  await expect(page.getByText("No song loaded yet")).toBeVisible();
});
