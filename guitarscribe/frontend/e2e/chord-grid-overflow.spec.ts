import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

const fixture=JSON.parse(readFileSync(new URL('../../backend/tests/fixtures/reviewed_live_chord_entry.json',import.meta.url),'utf8'));

for(const width of [1440,1000,390])test(`tiny chord fragments stay inside the measure at ${width}px`,async({page})=>{
  await page.setViewportSize({width,height:900});
  await page.route('**/api/v1/capabilities',r=>r.fulfill({json:{youtube_enabled:false,melody_available:true}}));
  await page.route('**/api/v1/jobs/geometry',r=>r.fulfill({json:{id:'geometry',status:'completed',progress:100,artifacts:[],score:fixture.score}}));
  await page.route('**/rhythm-patterns?*',r=>r.fulfill({json:[]}));
  await page.goto('/?job=geometry');await page.getByRole('button',{name:'伴奏演奏',exact:true}).click();
  const results=await page.locator('.measure-card').evaluateAll(cards=>cards.map(card=>{
    const ruler=card.querySelector('.measure-beat-ruler')!.getBoundingClientRect();
    const track=card.querySelector('.measure-chords')!.getBoundingClientRect();
    const blocks=[...card.querySelectorAll<HTMLElement>('.chord-block')].map(el=>{
      const box=el.getBoundingClientRect();const [from,to]=el.style.gridColumn.split('/').map(Number);
      return {left:box.left-track.left,right:box.right-track.right,width:box.width,
        expectedWidth:(to-from)/1000*track.width};
    });
    return {rulerWidth:ruler.width,trackWidth:track.width,blocks};
  }));
  expect(results.length).toBeGreaterThan(0);
  expect(results.flatMap(r=>r.blocks).some(b=>b.expectedWidth<10)).toBe(true);
  for(const r of results){expect(Math.abs(r.rulerWidth-r.trackWidth)).toBeLessThan(.1);
    for(const b of r.blocks){expect(b.left).toBeGreaterThanOrEqual(-.1);expect(b.right).toBeLessThanOrEqual(.1);expect(Math.abs(b.width-b.expectedWidth)).toBeLessThan(.1);}}
});
