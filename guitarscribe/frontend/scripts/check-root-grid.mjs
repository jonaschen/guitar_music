// Read-only verification of the manual grid against an existing invited song.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:5273',job=process.env.ROOT_PRACTICE_JOB||'83a3643ab3814172a046cebf709f3413';
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const out=new URL('../../output/evaluation/root-practice-grid-2026-11-12/',import.meta.url);await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
  const context=await browser.newContext({httpCredentials:{...credentials,send:'always'},viewport:{width:1440,height:1000}});
  await context.route(base+'/**',route=>route.continue({headers:{...route.request().headers(),authorization:'Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64')}}));
  const prefix=base+'/backend/api/v1/jobs/'+job;
  const get=async url=>{const r=await context.request.get(url);if(!r.ok())throw Error('GET '+r.status());return r.json();};
  const score=await get(prefix),sheet=await get(prefix+'/root-practice');
  const chosen=sheet.document.segments.find(s=>s.start>=15&&s.end-s.start>=1)??sheet.document.segments[0],anchor=Math.round((chosen.start+.123)*1000)/1000;
  const page=await context.newPage(),errors=[],writes=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(['PUT','DELETE'].includes(r.method())||(r.method()==='POST'&&!r.url().endsWith('/root-candidates/rank')))writes.push(r.method()+' '+new URL(r.url()).pathname);});
  await page.addInitScript(()=>{
    window.__gridAudio=[];const values=new WeakMap(),setValue=AudioParam.prototype.setValueAtTime;
    AudioParam.prototype.setValueAtTime=function(value,time){values.set(this,value);return setValue.call(this,value,time);};
    for(const [kind,prototype]of [['tone',OscillatorNode.prototype],['source',AudioBufferSourceNode.prototype]]){
      const start=prototype.start;prototype.start=function(...args){window.__gridAudio.push({kind,at:args[0],offset:args[1],loop:this.loop,loopStart:this.loopStart,loopEnd:this.loopEnd,hz:values.get(this.frequency)});return start.apply(this,args);};
    }
  });
  await page.goto(base+'/root-practice-2026-11-12/?practice=roots&job='+job);
  await page.getByLabel('節拍器 BPM',{exact:true}).waitFor();
  await page.getByLabel('小節對齊全曲定位',{exact:true}).evaluate((el,value)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(value));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));},anchor);
  await page.getByRole('button',{name:'目前位置設為小節起點',exact:true}).click();
  if(Number(await page.getByLabel('小節對齊點秒數').inputValue())!==anchor)throw Error('Anchor mismatch');
  await page.getByRole('navigation',{name:'附近小節'}).locator('[aria-current=step]').click();
  const start=Number(await page.getByLabel('連聽起點秒數').inputValue()),end=Number(await page.getByLabel('連聽終點秒數').inputValue());
  if(Math.abs(start-anchor)>1e-8||Math.abs(end-start-240/115)>1e-8)throw Error('Incorrect bar range');
  await page.getByLabel('播放時加入節拍聲',{exact:true}).check();
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:900});if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Overflow '+width);
    await page.getByRole('region',{name:'節拍與小節對齊',exact:true}).screenshot({path:new URL(`grid-${job}-${width}.png`,out).pathname});
  }
  await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();await page.getByRole('button',{name:'暫停',exact:true}).waitFor({timeout:45000});await page.waitForTimeout(2600);
  let records=await page.evaluate(()=>window.__gridAudio),sources=records.filter(r=>r.kind==='source'),clicks=records.filter(r=>r.kind==='tone'&&r.hz>=900),roots=records.filter(r=>r.kind==='tone'&&r.hz<900);
  if(sources.length!==1||!sources[0].loop||sources[0].offset!==start)throw Error('Discontinuous source');
  if(clicks.length<5)throw Error('No looped metronome');
  clicks.forEach((click,i)=>{if(Math.abs(click.at-sources[0].at-i*60/115)>.003||click.hz!==(i%4===0?1400:900))throw Error('Beat clock or accent mismatch');});
  for(const tone of roots){const position=start+((tone.at-sources[0].at)%(end-start));const segment=sheet.document.segments.find(s=>position>=s.start-.001&&position<s.end-.001);if(!segment||segment.status!=='confirmed'||Math.abs(tone.hz-440*2**((40+(segment.root-4+12)%12-69)/12))>.001)throw Error('Unexpected adopted root');}
  await page.getByRole('button',{name:'延後 10 ms',exact:true}).click();await page.waitForTimeout(650);
  records=await page.evaluate(()=>window.__gridAudio);if(records.filter(r=>r.kind==='source').length!==1)throw Error('Realignment restarted source');
  await page.getByRole('button',{name:'暫停範圍',exact:true}).click();await page.reload();await page.getByLabel('小節對齊點秒數').waitFor();
  if(Math.abs(Number(await page.getByLabel('小節對齊點秒數').inputValue())-anchor-.01)>1e-8)throw Error('Alignment not restored');
  const after=await get(prefix),saved=await get(prefix+'/root-practice');if(JSON.stringify(after.score)!==JSON.stringify(score.score)||JSON.stringify(saved)!==JSON.stringify(sheet))throw Error('Score/practice changed during read-only check');
  if(errors.length||writes.length)throw Error('Unexpected page error or write');
  const result={job,bpm:115,beats_per_bar:4,anchor,start,end,bar_seconds:end-start,metronome_clicks:clicks.length,adopted_root_starts:roots.length,beat_clock_and_accents_correct:true,live_shift_keeps_source:true,settings_restored:true,widths:[320,390,768,1440],page_errors:errors,writes,score_and_practice_unchanged:true};await fs.writeFile(new URL(`grid-${job}.json`,out),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
