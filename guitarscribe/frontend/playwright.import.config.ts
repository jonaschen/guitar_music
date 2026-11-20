import {defineConfig} from '@playwright/test';
const baseURL='http://127.0.0.1:4195';
export default defineConfig({testDir:'./e2e',testMatch:'**/analysis-start.spec.ts',workers:1,timeout:45000,
 use:{baseURL,launchOptions:process.env.GUITARSCRIBE_CHROME?{executablePath:process.env.GUITARSCRIBE_CHROME}:{},
 storageState:{cookies:[],origins:[{origin:baseURL,localStorage:[{name:'guitarscribe.workspaceMode',value:'full'},{name:'guitarscribe.editorView',value:'melody'}]}]}},
 webServer:{command:'npm run dev -- --host 127.0.0.1 --port 4195 --strictPort',url:baseURL,reuseExistingServer:false,
 env:{VITE_ARCHIVED_MELODY:'true',GUITARSCRIBE_API_TARGET:'http://127.0.0.1:5299'}}});
