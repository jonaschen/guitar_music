// Read-only validation from the published main page to the current-song visual workspace.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:5273',output=new URL('../../output/evaluation/visual-main-entry-2026-11-17/',import.meta.url);
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const errors=[],writes=[],results=[];
try{
 for(const job of [null,'83a3643ab3814172a046cebf709f3413','a3be29912a7045448765290d7cba2f6c']){
  const context=await browser.newContext({httpCredentials:{username:credentials.username,password:credentials.password,origin:base,send:'always'},viewport:{width:1440,height:1000}});
  const auth='Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64');
  await context.route(base+'/**',route=>{const r=route.request();if(!['GET','HEAD'].includes(r.method())&&!new URL(r.url()).pathname.endsWith('/root-candidates/rank')){writes.push(r.method()+' '+new URL(r.url()).pathname);return route.abort();}return route.continue({headers:{...r.headers(),authorization:auth}});});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+(job?'/?job='+job:'/'),{waitUntil:'domcontentloaded'});
  if(job)await page.getByRole('navigation',{name:'工作區模式'}).waitFor();
  const entry=page.getByRole('button',{name:'視覺化練習',exact:true});await entry.waitFor();
  await page.screenshot({path:new URL(`${job??'empty'}-main.png`,output).pathname,fullPage:false});
  await entry.click();
  await page.waitForURL(url=>url.pathname==='/visual-practice-2026-11-14/'&&url.searchParams.get('practice')==='roots'&&url.searchParams.get('visual')==='1'&&url.searchParams.get('job')===job);
  if(job){await page.getByRole('main',{name:'根音抓歌練習'}).waitFor();await page.getByRole('slider',{name:'頻譜定位時間'}).waitFor({timeout:60000});}
  else await page.getByRole('heading',{name:'一起抓出歌曲的根音'}).waitFor();
  results.push({job,main_entry_visible:true,current_song_preserved:true,visual_open:!!job,url:page.url().replace(base,'')});await context.close();
 }
 if(errors.length||writes.length)throw Error(JSON.stringify({errors,writes}));
 const report={results,errors,writes};await fs.writeFile(new URL('browser.json',output),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
}finally{await browser.close();}
