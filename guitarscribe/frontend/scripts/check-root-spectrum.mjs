// Read-only integration against existing invited sources. No decision writes.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base='http://127.0.0.1:5273';
const pagePath='/visual-practice-2026-11-14/';
const root=new URL('../../output/evaluation/root-spectrum-source-only-2026-11-14/',import.meta.url);
await fs.mkdir(root,{recursive:true});
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const context=await browser.newContext({httpCredentials:{username:credentials.username,password:credentials.password,send:'always'},viewport:{width:1440,height:1100}});
await context.addInitScript(()=>{
  window.__spectrumAudio={sources:0,tones:0};
  const sourceStart=AudioBufferSourceNode.prototype.start,toneStart=OscillatorNode.prototype.start;
  AudioBufferSourceNode.prototype.start=function(...args){window.__spectrumAudio.sources++;return sourceStart.apply(this,args);};
  OscillatorNode.prototype.start=function(...args){window.__spectrumAudio.tones++;return toneStart.apply(this,args);};
});
await context.route(base+'/**',route=>route.continue({headers:{...route.request().headers(),authorization:'Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64')}}));
const hash=value=>createHash('sha256').update(JSON.stringify(value)).digest('hex');
const get=async path=>{const response=await context.request.get(base+'/backend/api/v1/jobs/'+path);if(!response.ok())throw Error('GET failed '+response.status());return response.json();};
const results=[];
try{
  for(const job of ['83a3643ab3814172a046cebf709f3413','a3be29912a7045448765290d7cba2f6c']){
    const before=await get(job),saved=await get(job+'/root-practice'),errors=[],writes=[];
    const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>{if(['PUT','DELETE'].includes(r.method())||r.method()==='POST'&&!new URL(r.url()).pathname.endsWith('/root-candidates/rank'))writes.push(r.method()+' '+new URL(r.url()).pathname);});
    await page.goto(base+pagePath+'?practice=roots&visual=1&job='+job);
    await page.getByRole('button',{name:'產生低頻圖',exact:true}).waitFor({timeout:30000});
    if(await page.getByText('練習設定與進階工具',{exact:true}).count())await page.getByText('練習設定與進階工具',{exact:true}).click();
    const start=Date.now();await page.getByRole('button',{name:'產生低頻圖',exact:true}).click();
    await page.getByLabel('頻譜狀態').filter({hasText:'已就緒'}).waitFor({timeout:120000});
    const elapsed=Date.now()-start;
    if((await page.getByLabel('頻譜狀態').innerText()).includes('已隱藏'))throw Error('Original chord source did not match');
    const chordCount=await page.getByLabel('原分析和弦時間軸').getByRole('button').count();
    if(chordCount===0)throw Error('Expected original chords in the initial view');
    const unique=await page.locator('.root-spectrum canvas').evaluate(el=>{
      const data=el.getContext('2d').getImageData(0,0,el.width,el.height).data,colors=new Set();
      for(let i=0;i<data.length;i+=16)colors.add(data[i]+','+data[i+1]+','+data[i+2]);return colors.size;
    });
    if(unique<20)throw Error('Spectrogram has no visible structure');
    const chart=page.getByRole('slider',{name:'頻譜定位時間'});
    await page.getByRole('button',{name:'看全曲',exact:true}).click();
    await chart.focus();await page.keyboard.press('Home');
    await page.getByRole('button',{name:'看 10 秒',exact:true}).click();
    await chart.scrollIntoViewIfNeeded();
    const box=await chart.boundingBox();
    await page.mouse.move(box.x+box.width*.25,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.5,{steps:12});await page.mouse.up();
    const a=Number(await page.getByLabel('連聽起點秒數').inputValue()),b=Number(await page.getByLabel('連聽終點秒數').inputValue());
    if(Math.abs(a-2.5)>.03||Math.abs(b-6.5)>.03)throw Error('Drag range time mismatch '+JSON.stringify({a,b}));
    await page.getByRole('button',{name:'循環 A–B 原曲',exact:true}).click();
    await page.getByRole('button',{name:'暫停圖表播放',exact:true}).waitFor({timeout:45000});
    const moving=await page.waitForFunction(({a,b})=>{
      const position=Number(document.querySelector('[aria-label="頻譜定位時間"]')?.getAttribute('aria-valuenow'));
      return position>a+.2&&position<b?position:false;
    },{a,b},{timeout:5000});
    const position=await moving.jsonValue();
    await page.getByRole('button',{name:'暫停圖表播放',exact:true}).click();
    const audio=await page.evaluate(()=>window.__spectrumAudio);
    if(audio.sources<1||audio.tones!==0)throw Error('Expected original audio without added root tones: '+JSON.stringify(audio));
    if(await page.getByLabel('根音練習聲音').inputValue()!=='source')throw Error('Source-only mode not retained');
    for(const width of [320,390,768,1440]){
      await page.setViewportSize({width,height:1100});
      if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Page overflow '+width);
      await page.locator('.root-spectrum').screenshot({path:new URL(`${job}-${width}.png`,root).pathname});
    }
    const after=await get(job),savedAfter=await get(job+'/root-practice');
    if(hash(before.score)!==hash(after.score)||hash(saved)!==hash(savedAfter))throw Error('Existing score or practice changed during readonly check');
    if(writes.length||errors.length)throw Error(JSON.stringify({writes,errors}));
    results.push({job,duration:saved.document.source.duration,generation_ms:elapsed,distinct_sampled_colors:unique,original_chords_in_view:chordCount,range:[a,b],playback_position:position,audio,widths:[320,390,768,1440],source_score_unchanged:true,practice_unchanged:true,unexpected_writes:writes,page_errors:errors});
    await page.close();
  }
  await fs.writeFile(new URL('browser.json',root),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
}finally{await browser.close();}
