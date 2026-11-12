import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/root-practice.spec.ts',workers:1,timeout:45000,
  use:{baseURL:'http://127.0.0.1:4176',browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}},
  webServer:{command:'VITE_ARCHIVED_MELODY=false npm run dev -- --host 127.0.0.1 --port 4176 --strictPort',url:'http://127.0.0.1:4176',reuseExistingServer:false,timeout:120000}});
