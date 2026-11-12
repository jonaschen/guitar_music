// Read-only verification of the published range player with a real source.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:5273',job=process.env.ROOT_PRACTICE_JOB||'83a3643ab3814172a046cebf709f3413';
const credentials=JSON.parse(await fs.readFile(new URL('../../output/web-preview/access.json',import.meta.url),'utf8'));
const out=new URL('../../output/evaluation/root-practice-range-2026-11-12/',import.meta.url);await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
try{
  const context=await browser.newContext({httpCredentials:{...credentials,send:'always'},viewport:{width:1440,height:1000}});
  await context.route(base+'/**',route=>route.continue({headers:{...route.request().headers(),authorization:'Basic '+Buffer.from(credentials.username+':'+credentials.password).toString('base64')}}));
  const prefix=base+'/backend/api/v1/jobs/'+job;
  const get=async url=>{const r=await context.request.get(url);if(!r.ok())throw Error('GET '+r.status());return r.json();};
  const before=await get(prefix),sheet=await get(prefix+'/root-practice');
  const segments=sheet.document.segments,chosen=segments.find(s=>s.start>=15&&s.end-s.start>=1)??segments[0];
  const start=chosen.start+.1,end=Math.min(start+4,sheet.document.source.duration);
  const page=await context.newPage(),errors=[],mutations=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(['POST','PUT','DELETE'].includes(r.method()))mutations.push({method:r.method(),path:new URL(r.url()).pathname});});
  await page.addInitScript(()=>{
    window.__rangeAudio=[];const values=new WeakMap(),setValue=AudioParam.prototype.setValueAtTime;
    AudioParam.prototype.setValueAtTime=function(value,time){values.set(this,value);return setValue.call(this,value,time);};
    for(const [kind,prototype]of [['tone',OscillatorNode.prototype],['source',AudioBufferSourceNode.prototype]]){
      const start=prototype.start;
      prototype.start=function(...args){window.__rangeAudio.push({kind,at:args[0],offset:args[1],loop:this.loop,loopStart:this.loopStart,loopEnd:this.loopEnd,hz:values.get(this.frequency)});return start.apply(this,args);};
    }
  });
  await page.goto(base+'/root-practice-2026-11-12/?practice=roots&job='+job);
  await page.getByRole('region',{name:'範圍連聽',exact:true}).waitFor();
  await page.getByText('微調範圍時間',{exact:true}).click();await page.getByLabel('連聽起點秒數').fill(String(start));await page.getByLabel('連聽終點秒數').fill(String(end));
  for(const width of [320,390,768,1440]){
    await page.setViewportSize({width,height:900});
    if(!await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw Error('Overflow '+width);
    await page.getByRole('region',{name:'範圍連聽',exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:new URL(`range-${job}-${width}.png`,out).pathname,fullPage:true});
  }
  await page.getByRole('button',{name:'播放選取範圍',exact:true}).click();await page.getByRole('button',{name:'暫停',exact:true}).waitFor({timeout:45000});
  await page.waitForTimeout(Math.ceil((end-start)*1000)+300);
  const records=await page.evaluate(()=>window.__rangeAudio),sources=records.filter(r=>r.kind==='source'),tones=records.filter(r=>r.kind==='tone');
  if(sources.length!==1||!sources[0].loop||sources[0].loopStart!==start||sources[0].loopEnd!==end||sources[0].offset!==start)throw Error('Source range mismatch');
  for(const tone of tones){
    const position=start+(((tone.at-sources[0].at)%(end-start))+(end-start))%(end-start);
    const decision=segments.find(s=>position>=s.start-.001&&position<s.end-.001);
    if(!decision||decision.status!=='confirmed'||decision.root===null)throw Error('Tone in undecided segment');
    if(Math.abs(tone.hz-440*2**((40+(decision.root-4+12)%12-69)/12))>.001)throw Error('Wrong adopted root');
  }
  await page.getByRole('button',{name:'暫停範圍',exact:true}).click();
  const after=await get(prefix),saved=await get(prefix+'/root-practice');
  if(JSON.stringify(after.score)!==JSON.stringify(before.score)||JSON.stringify(saved)!==JSON.stringify(sheet))throw Error('Read-only playback changed data');
  if(errors.length||mutations.some(r=>r.method!=='POST'||!r.path.endsWith('/root-candidates/rank')))throw Error('Unexpected page error or write');
  const result={job,start,end,source_continuous_and_looped:true,adopted_root_starts:tones.length,unknown_segments_do_not_add_tones:true,source_score_unchanged:true,practice_unchanged:true,page_errors:errors,widths:[320,390,768,1440]};
  await fs.writeFile(new URL(`range-${job}.json`,out),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
