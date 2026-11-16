import {test,expect,type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

const template=readFileSync(new URL('../../backend/app/evaluation/song_structure_review.html',import.meta.url),'utf8');
const candidates=[{title:'測試主歌副歌',job:'song-one',fingerprint:'a'.repeat(64),duration:8,source_start:42,sections:[
  {start:0,end:2,display_label:'前奏'},{start:2,end:4,display_label:'主歌'},{start:4,end:8,display_label:'副歌'}]},
  {title:'沒有前奏的歌',job:'song-two',fingerprint:'b'.repeat(64),duration:8,source_start:0,sections:[{start:0,end:8,display_label:'副歌'}]}];
function wav(){const n=8000*8,b=Buffer.alloc(44+n*2);b.write('RIFF');b.writeUInt32LE(36+n*2,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(8000,24);b.writeUInt32LE(16000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n*2,40);return b;}
async function setup(page:Page,broken=false){
  const writes:string[]=[],sources:string[]=[];
  await page.route('http://structure.test/**',async route=>{
    const r=route.request();if(r.method()!=='GET')writes.push(r.method());
    if(r.url().includes('/root-practice/audio')){
      sources.push(r.url());if(broken)return route.fulfill({status:409});
      const body=wav(),match=/bytes=(\d+)-(\d*)/.exec(r.headers().range??'');
      if(match){const start=Number(match[1]),end=match[2]?Math.min(Number(match[2]),body.length-1):body.length-1;
        return route.fulfill({status:206,body:body.subarray(start,end+1),contentType:'audio/wav',headers:{'accept-ranges':'bytes','content-range':`bytes ${start}-${end}/${body.length}`}});}
      return route.fulfill({body,contentType:'audio/wav',headers:{'accept-ranges':'bytes'}});
    }
    return route.fulfill({body:template.replace('__CANDIDATES__',JSON.stringify(candidates)),contentType:'text/html'});
  });
  await page.goto('http://structure.test/',{waitUntil:'domcontentloaded'});return{writes,sources};
}

test('structure review shows semantic draft labels, uses source-local time and stops at selected end',async({page})=>{
  const {writes,sources}=await setup(page);
  await expect(page.getByText('尚未確認正確',{exact:true})).toBeVisible();
  await expect(page.locator('.section')).toHaveCount(3);
  const verse=page.getByRole('region',{name:'第 2 段 主歌',exact:true});
  await verse.getByRole('button',{name:'聽這段',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('正在聽：主歌');
  await expect.poll(()=>page.locator('audio').evaluate(el=>(el as HTMLAudioElement).currentTime)).toBeGreaterThanOrEqual(2);
  await expect.poll(()=>page.locator('audio').evaluate(el=>(el as HTMLAudioElement).paused)).toBe(true);
  const end=await page.locator('audio').evaluate(el=>(el as HTMLAudioElement).currentTime);
  expect(end).toBeGreaterThanOrEqual(4);expect(end).toBeLessThan(4.5);
  expect(sources[0]).toContain('song-one/root-practice/audio?fingerprint=');expect(writes).toEqual([]);
});

test('structure boundary audition and switching songs do not reuse previous bounds or add fake sections',async({page})=>{
  const {writes}=await setup(page);
  await page.getByRole('region',{name:'第 3 段 副歌',exact:true}).getByRole('button',{name:'聽交界',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('副歌的交界 0:01.0–0:07.0');
  await page.getByLabel('選擇歌曲').selectOption('1');
  await expect(page.locator('.section')).toHaveCount(1);
  expect(await page.locator('audio').evaluate(el=>(el as HTMLAudioElement).paused)).toBe(true);
  await expect(page.locator('audio')).toHaveAttribute('src',/song-two/);
  await expect(page.getByRole('link',{name:'回到這首歌的根音練習'})).toHaveAttribute('href',/job=song-two/);
  expect(writes).toEqual([]);
});

test('structure review keeps the draft readable if original audio is unavailable',async({page})=>{
  await setup(page,true);
  await expect(page.getByRole('alert')).toContainText('原曲載入失敗');
  await expect(page.locator('.section')).toHaveCount(3);
});

for(const width of [320,390,768,1440])test(`structure review fits ${width}px and exposes keyboard controls`,async({page})=>{
  await page.setViewportSize({width,height:900});await setup(page);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  const button=page.getByRole('button',{name:'聽這段',exact:true}).first();await button.focus();
  await expect(button).toBeFocused();
  expect(await button.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe('solid');
});

test('sub-frame tail is explicit and directs audition to its boundary',async({page})=>{
  await page.route('http://structure.test/**',route=>route.request().url().includes('/root-practice/audio')
    ?route.fulfill({body:wav(),contentType:'audio/wav'})
    :route.fulfill({contentType:'text/html',body:template.replace('__CANDIDATES__',JSON.stringify([
      {...candidates[0],sections:[{start:0,end:7.998,display_label:'尾奏'},{start:7.998,end:8,display_label:'結尾未判定'}]}
    ]))}));
  await page.goto('http://structure.test/',{waitUntil:'domcontentloaded'});
  const tail=page.getByRole('region',{name:'第 2 段 結尾未判定',exact:true});
  await expect(tail).toContainText('少於 0.1 秒');
  await expect(tail.getByRole('button',{name:'聽這段',exact:true})).toBeDisabled();
  await expect(tail.getByRole('button',{name:'聽交界',exact:true})).toBeEnabled();
});

test('user feedback shows original numbering and separates name from boundary confirmation',async({page})=>{
  const revised={...candidates[0],feedback:{date:'2026-11-17'},sections:[
    {start:0,end:2,display_label:'前奏',original_numbers:[1,2],name_review_status:'user_confirmed',removed_internal_boundaries:[1]},
    {start:2,end:4,display_label:'副歌',original_numbers:[8],name_review_status:'user_corrected'},
    {start:4,end:8,display_label:'收尾段（較接近主歌）',original_numbers:[12],name_review_status:'user_corrected'}]};
  await page.route('http://structure.test/**',route=>route.request().url().includes('/root-practice/audio')
    ?route.fulfill({body:wav(),contentType:'audio/wav'})
    :route.fulfill({contentType:'text/html',body:template.replace('__CANDIDATES__',JSON.stringify([revised,candidates[1]]))}));
  await page.goto('http://structure.test/',{waitUntil:'domcontentloaded'});
  await expect(page.locator('#summary')).not.toContainText('全部待確認');
  const intro=page.locator('.section').first();
  await expect(intro).toContainText('原第 1、2 段');
  await expect(intro).toContainText('名稱已確認');
  await expect(intro).toContainText('外側邊界待確認');
  await expect(page.locator('.section').nth(1)).toContainText('原第 8 段');
  await expect(page.locator('.section').nth(2)).toContainText('收尾段（較接近主歌）');
  await page.getByLabel('選擇歌曲').selectOption('1');
  await expect(page.locator('#summary')).toContainText('全部待確認');
  await expect(page.locator('.section')).not.toContainText('名稱已確認');
});
