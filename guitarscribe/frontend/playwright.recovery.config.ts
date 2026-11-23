import {defineConfig} from '@playwright/test';
const python=process.env.GUITARSCRIBE_TEST_PYTHON??'python3';
const quote=(v:string)=>"'"+v.replaceAll("'","'\\''")+"'";
export default defineConfig({testDir:'./e2e',testMatch:'**/analysis-recovery-fullstack.spec.ts',workers:1,timeout:60000,
 outputDir:'../output/recovery-test-results',use:{baseURL:'http://127.0.0.1:5296',trace:'retain-on-failure'},
 projects:[{name:'recovery-chromium',use:{browserName:'chromium'}},{name:'recovery-webkit',use:{browserName:'webkit'}}],
 webServer:{command:`${quote(python)} ../backend/scripts/serve_recovery_fixture.py --frontend dist --port 5296`,
 url:'http://127.0.0.1:5296',reuseExistingServer:false,timeout:120000}});
