import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: "**/chord-product.spec.ts",
  // Legacy suites explicitly exercise melody editing and the complete toolset.
  // accompaniment-review.spec.ts clears both preferences to cover the new-user default.
  use: { baseURL: "http://127.0.0.1:4173", browserName: "chromium", launchOptions: { executablePath: "/usr/bin/google-chrome" },
    storageState: { cookies: [], origins: ["http://127.0.0.1:4173", "http://127.0.0.1:5173"].map(origin => ({ origin, localStorage: [{ name: "guitarscribe.workspaceMode", value: "full" }, { name: "guitarscribe.editorView", value: "melody" }] })) } },
  webServer: {
    command: "VITE_ARCHIVED_MELODY=true npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
  },
});
