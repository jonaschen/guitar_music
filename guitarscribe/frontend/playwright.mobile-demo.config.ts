import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/mobile-demo.spec.ts',workers:1,timeout:45000,
 use:{...devices['Pixel 7'],baseURL:'http://127.0.0.1:4181',browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}},
 webServer:{command:'npm run dev -- --host 127.0.0.1 --port 4181 --strictPort',url:'http://127.0.0.1:4181',reuseExistingServer:false,timeout:120000}});
