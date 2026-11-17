import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',testMatch:'**/section-chords-fullstack.spec.ts',workers:1,timeout:60000,
 use:{baseURL:'http://127.0.0.1:5289',browserName:'chromium',launchOptions:{executablePath:'/usr/bin/google-chrome'}},
 webServer:{command:'/home/jonas/.cache/guitarscribe-runtime/bin/python ../backend/scripts/serve_chord_practice_fixture.py --frontend dist --port 5289',url:'http://127.0.0.1:5289',reuseExistingServer:false,timeout:120000}});
