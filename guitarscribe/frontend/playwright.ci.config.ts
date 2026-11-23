import {defineConfig,devices} from '@playwright/test';

// Every spec runs in exactly one environment. The existing split configs remain
// useful for focused development; this is the complete, isolated CI entrypoint.
const python=process.env.GUITARSCRIBE_TEST_PYTHON??'python3';
const quote=(value:string)=>"'"+value.replaceAll("'","'\\''")+"'";
const api='http://127.0.0.1:5290';
process.env.GUITARSCRIBE_API_URL=api;
process.env.GUITARSCRIBE_TEST_PYTHON=python;
const normal='http://127.0.0.1:4191',legacy='http://127.0.0.1:4190';
const modern=['chord-product','root-practice','root-reuse','section-chords','structure-editor','song-structure'].map(n=>`**/${n}.spec.ts`);
const fullstack=['structure','root-reuse','section-chords','learning-practice','analysis-recovery'].map(n=>`**/${n}-fullstack.spec.ts`);
const launchOptions=process.env.GUITARSCRIBE_CHROME ? {executablePath:process.env.GUITARSCRIBE_CHROME}:{};
const vite=(port:number,archived:boolean)=>({
 command:`npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,url:`http://127.0.0.1:${port}`,
 env:{VITE_ARCHIVED_MELODY:String(archived),GUITARSCRIBE_API_TARGET:api},reuseExistingServer:false,timeout:120000});
export default defineConfig({testDir:'./e2e',workers:1,timeout:45000,retries:0,
 use:{browserName:'chromium',launchOptions,trace:'retain-on-failure'},
 webServer:[
  {command:`${quote(python)} scripts/serve-ci-api.py`,url:api+'/health',reuseExistingServer:false,timeout:120000},
  vite(4190,true),vite(4191,false),
  ...[
   ['serve_structure_fixture.py',5291],['serve_root_reuse_fixture.py',5292],['serve_chord_practice_fixture.py',5293],['serve_chord_practice_fixture.py',5294],
  ].map(([script,port])=>({command:`${quote(python)} ../backend/scripts/${script} --frontend dist --port ${port}`,
   url:`http://127.0.0.1:${port}`,reuseExistingServer:false,timeout:120000})),
 ],
 projects:[
  {name:'legacy-editor',testIgnore:[...modern,...fullstack,'**/mobile-demo.spec.ts'],use:{baseURL:legacy,
   storageState:{cookies:[],origins:[legacy].map(origin=>({origin,localStorage:[
    {name:'guitarscribe.workspaceMode',value:'full'},{name:'guitarscribe.editorView',value:'melody'}]}))}}},
  {name:'practice',testMatch:modern,use:{baseURL:normal}},
  {name:'mobile-demo',testMatch:'**/mobile-demo.spec.ts',use:{...devices['Pixel 7'],baseURL:normal}},
  ...['structure','root-reuse','section-chords','learning-practice'].map((name,i)=>({name:name+'-api',testMatch:`**/${name}-fullstack.spec.ts`,
   timeout:60000,use:{baseURL:`http://127.0.0.1:${5291+i}`}})),
 ],
});
