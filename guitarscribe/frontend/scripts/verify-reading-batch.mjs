import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const out=new URL('../../output/evaluation/reading-candidate-2026-11-05/',import.meta.url);
const bytes=await readFile(new URL('sources.json',out));
const frozen=JSON.parse(await readFile(new URL('frozen-preview-manifest.json',out),'utf8'));
assert.equal(createHash('sha256').update(bytes).digest('hex'),frozen.sources_file_sha256);
const sources=JSON.parse(bytes),browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true});
const rows=[];
try{
  for(const source of sources){
    const context=await browser.newContext(),page=await context.newPage();let writes=0;const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/backend/**',r=>{
      const path=new URL(r.request().url()).pathname;
      if(r.request().method()!=='GET'){writes++;return r.fulfill({status:409});}
      if(path.endsWith('/timing-preview'))return r.fulfill({json:source.preview});
      if(path.endsWith('/jobs/'+source.job.id))return r.fulfill({json:source.job});
      if(path.endsWith('/capabilities'))return r.fulfill({json:{melody_available:false,youtube_enabled:true}});
      if(path.includes('/history')||path.includes('/chord-voicings')||path.includes('/rhythm-patterns'))return r.fulfill({json:[]});
      return r.fulfill({status:404});
    });
    await page.goto('http://127.0.0.1:4181/?job='+source.job.id+'&timingView=auto');
    await page.getByRole('region',{name:'和弦核對'}).waitFor();
    const expected=source.metered?0:source.preview.regions.reduce((n,r)=>n+r.bars.length,0);
    if(expected){await page.getByLabel('局部小節預覽',{exact:true}).waitFor();assert.equal(await page.locator('.partial-timing-sheet .notation-measure').count(),expected);}
    else assert.equal(await page.getByLabel('讀譜方式',{exact:true}).count(),0);
    for(const width of [320,390,1440]){
      await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    }
    assert.equal(writes,0);assert.deepEqual(errors,[]);
    rows.push({job_id:source.job.id,expected_local_bars:expected,metered:source.metered,viewports:[320,390,1440],writes,page_errors:errors});
    await context.close();
  }
  await writeFile(new URL('browser-batch.json',out),JSON.stringify({source_count:rows.length,rows},null,2));
  console.log(JSON.stringify({sources:rows.length,viewport_checks:rows.length*3,writes:0,page_errors:0}));
}finally{await browser.close();}
