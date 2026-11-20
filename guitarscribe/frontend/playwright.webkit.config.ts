import {defineConfig,devices} from '@playwright/test';
const baseURL='http://127.0.0.1:4196';
export default defineConfig({testDir:'./e2e',outputDir:'../output/webkit-test-results',workers:1,timeout:45000,
 use:{baseURL,browserName:'webkit',trace:'retain-on-failure'},
 webServer:{command:'npm run dev -- --host 127.0.0.1 --port 4196 --strictPort',url:baseURL,reuseExistingServer:false,
 env:{VITE_ARCHIVED_MELODY:'false',GUITARSCRIBE_API_TARGET:'http://127.0.0.1:5299'}},
 projects:[{name:'phone-webkit',testMatch:'**/mobile-demo.spec.ts',use:{...devices['iPhone 13']}},
  {name:'practice-webkit',testMatch:'**/section-chords.spec.ts'}]});
