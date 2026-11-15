import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/song-structure.spec.ts',workers:1,timeout:30000,
  use:{browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}}});
