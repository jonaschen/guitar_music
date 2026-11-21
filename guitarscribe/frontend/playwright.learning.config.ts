import {defineConfig} from '@playwright/test';
const python=process.env.GUITARSCRIBE_TEST_PYTHON??'python3';
export default defineConfig({testDir:'./e2e',testMatch:'**/learning-practice-fullstack.spec.ts',workers:1,timeout:120000,outputDir:'../output/learning-test-results',
 use:{browserName:process.env.GUITARSCRIBE_TEST_BROWSER==='webkit'?'webkit':'chromium',baseURL:'http://127.0.0.1:5294',launchOptions:process.env.GUITARSCRIBE_TEST_BROWSER!=='webkit'&&process.env.GUITARSCRIBE_CHROME?{executablePath:process.env.GUITARSCRIBE_CHROME}:{}},
 webServer:{command:`${python} ../backend/scripts/serve_chord_practice_fixture.py --frontend dist --port 5294`,url:'http://127.0.0.1:5294',reuseExistingServer:false,timeout:120000}});
