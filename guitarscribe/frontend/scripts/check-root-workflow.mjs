// Read-only integration against existing invited sources. No decision writes.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
const base='http://127.0.0.1:5273';
const pagePath='/visual-practice-2026-11-14/';
const root=new URL('../../output/evaluation/root-workflow-2026-11-14/',import.meta.url);
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
    if(await page.locator('details.root-advanced').evaluate(el=>el.open))throw Error('Tools must begin folded');
    await page.getByLabel('目前判斷段落').waitFor();
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
    let box=await chart.boundingBox();
    await page.mouse.click(box.x+box.width*.7,box.y+box.height*.5);
    await page.getByRole('button',{name:'練習游標所在段',exact:true}).click();
    const target=await page.getByLabel('採用目標').innerText();
    const selected=await page.locator('.root-progression [aria-current=step]').getAttribute('aria-label');
    if(!target.includes('將記錄到')||!selected)throw Error('Missing explicit adoption target');
    await chart.evaluate(el=>el.scrollIntoView({block:'center'}));
    box=await chart.boundingBox();
    await page.mouse.move(box.x+box.width*.25,box.y+box.height*.5);await page.mouse.down();await page.mouse.move(box.x+box.width*.65,box.y+box.height*.5,{steps:12});await page.mouse.up();
    const a=Number(await page.getByLabel('連聽起點秒數').inputValue()),b=Number(await page.getByLabel('連聽終點秒數').inputValue());
    if(Math.abs(a-2.5)>.03||Math.abs(b-6.5)>.03)throw Error('Drag range time mismatch '+JSON.stringify({a,b}));
    await page.getByRole('button',{name:'播放原曲範圍',exact:true}).click();
    await page.getByRole('button',{name:'暫停播放',exact:true}).waitFor({timeout:45000});
    const moving=await page.waitForFunction(({a,b})=>{
      const position=Number(document.querySelector('[aria-label="頻譜定位時間"]')?.getAttribute('aria-valuenow'));
      return position>a+.2&&position<b?position:false;
    },{a,b},{timeout:5000});
    const position=await moving.jsonValue();
    const sourcesBefore=await page.evaluate(()=>window.__spectrumAudio.sources);
    await page.getByText('練習設定與進階工具',{exact:true}).click();
    await page.getByText('練習設定與進階工具',{exact:true}).click();
    if(await page.evaluate(()=>window.__spectrumAudio.sources)!==sourcesBefore)throw Error('Folding tools restarted the source');
    if(await page.getByLabel('採用目標').innerText()!==target)throw Error('Listening range changed adoption target');
    await page.getByRole('button',{name:'暫停播放',exact:true}).click();
    const audio=await page.evaluate(()=>window.__spectrumAudio);
    if(audio.sources<1||audio.tones!==0)throw Error('Expected original audio without added root tones: '+JSON.stringify(audio));
    if(await page.getByLabel('根音練習聲音').inputValue()!=='source')throw Error('Source-only mode not retained');
    for(const width of [320,390,768,1440]){
      await page.setViewportSize({width,height:1100});
      if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Page overflow '+width);
      if(width<=390){
        const adopt=page.getByRole('button',{name:'採用這個根音',exact:true});
        await adopt.evaluate(el=>el.scrollIntoView({block:'center'}));
        const visible=await adopt.evaluate(el=>{
          const r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
          return r.y>=0&&r.bottom<=innerHeight&&el.contains(hit);
        });
        const player=await page.getByRole('button',{name:'播放原曲範圍',exact:true}).boundingBox();
        if(!visible||player.y<0||player.y+player.height>1100)throw Error('Pinned player or adoption control obscured at '+width);
        await page.screenshot({path:new URL(`${job}-${width}-decision.png`,root).pathname});
      }
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.screenshot({fullPage:true,path:new URL(`${job}-${width}.png`,root).pathname});
    }
    const after=await get(job),savedAfter=await get(job+'/root-practice');
    if(hash(before.score)!==hash(after.score)||hash(saved)!==hash(savedAfter))throw Error('Existing score or practice changed during readonly check');
    if(writes.length||errors.length)throw Error(JSON.stringify({writes,errors}));
    results.push({job,duration:saved.document.source.duration,generation_ms:elapsed,distinct_sampled_colors:unique,original_chords_in_view:chordCount,range:[a,b],playback_position:position,adoption_target:target,selected_segment:selected,tools_fold_preserved_source:true,mobile_player_and_decision_unobscured:true,audio,widths:[320,390,768,1440],source_score_unchanged:true,practice_unchanged:true,unexpected_writes:writes,page_errors:errors});
    await page.close();
  }
  await fs.writeFile(new URL('browser.json',root),JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
}finally{await browser.close();}
