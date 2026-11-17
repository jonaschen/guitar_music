import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/root-reuse.spec.ts',workers:1,timeout:45000,
 use:{baseURL:'http://127.0.0.1:4178',browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}},
 webServer:{command:'npm run dev -- --host 127.0.0.1 --port 4178 --strictPort',url:'http://127.0.0.1:4178',reuseExistingServer:false,timeout:120000}});
