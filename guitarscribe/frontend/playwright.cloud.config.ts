import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/cloud-maintenance.spec.ts',workers:1,
 use:{launchOptions:process.env.GUITARSCRIBE_CHROME?{executablePath:process.env.GUITARSCRIBE_CHROME}:{}}});
