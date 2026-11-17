import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/root-reuse-fullstack.spec.ts',workers:1,timeout:45000,
 use:{baseURL:'http://127.0.0.1:5288',browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}},
 webServer:{command:'/home/jonas/.cache/guitarscribe-runtime/bin/python ../backend/scripts/serve_root_reuse_fixture.py --frontend dist --port 5288',url:'http://127.0.0.1:5288',reuseExistingServer:false,timeout:120000}});
