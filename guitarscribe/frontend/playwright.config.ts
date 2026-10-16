import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Existing suites exercise the complete toolset. focused-workspace.spec.ts
  // explicitly clears this preference to cover the new-user default.
  use: { baseURL: "http://127.0.0.1:4173", browserName: "chromium", launchOptions: { executablePath: "/usr/bin/google-chrome" },
    storageState: { cookies: [], origins: ["http://127.0.0.1:4173", "http://127.0.0.1:5173"].map(origin => ({ origin, localStorage: [{ name: "guitarscribe.workspaceMode", value: "full" }] })) } },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: true,
  },
});
