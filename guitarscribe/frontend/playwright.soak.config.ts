import {defineConfig} from '@playwright/test';
const python=process.env.GUITARSCRIBE_TEST_PYTHON??'python3';
export default defineConfig({testDir:'./soak',workers:1,retries:0,outputDir:'../output/soak-results',
 use:{baseURL:'http://127.0.0.1:5295',trace:'retain-on-failure',launchOptions:process.env.GUITARSCRIBE_CHROME?{executablePath:process.env.GUITARSCRIBE_CHROME}:{}},
 webServer:{command:`${python} ../backend/scripts/serve_chord_practice_fixture.py --frontend dist --port 5295`,url:'http://127.0.0.1:5295',reuseExistingServer:false,timeout:120000}});
