import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/section-chords.spec.ts',workers:1,timeout:45000,
 use:{baseURL:'http://127.0.0.1:4182',browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}},
 webServer:{command:'npm run dev -- --host 127.0.0.1 --port 4182 --strictPort',url:'http://127.0.0.1:4182',reuseExistingServer:false,timeout:120000}});
