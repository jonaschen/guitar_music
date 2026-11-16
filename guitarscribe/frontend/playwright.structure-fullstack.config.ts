import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/structure-fullstack.spec.ts',workers:1,timeout:45000,
 use:{baseURL:'http://127.0.0.1:5287',browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}},
 webServer:{command:'/home/jonas/.cache/guitarscribe-runtime/bin/python ../backend/scripts/serve_structure_fixture.py --frontend dist --port 5287',url:'http://127.0.0.1:5287',reuseExistingServer:false,timeout:120000}});
