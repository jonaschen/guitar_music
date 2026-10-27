import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e', testMatch:'**/chord-product.spec.ts', workers:2,
  use:{baseURL:'http://127.0.0.1:4174',browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}},
  webServer:{command:'VITE_ARCHIVED_MELODY=false npm run dev -- --host 127.0.0.1 --port 4174 --strictPort',url:'http://127.0.0.1:4174',reuseExistingServer:false},
});
