import { expect, test } from "@playwright/test";

test.beforeEach(async ({page}) => {
  await page.route("**/api/v1/capabilities", r => r.fulfill({json:{youtube_enabled:true,vocal_separation_enabled:true,improved_accompaniment:false,melody_available:true,beat_engine:"test",chord_engine:"test"}}));
});

for (const source of ["upload", "youtube"]) {
  test(`submits pre-analysis skip for ${source}`, async ({ page }) => {
    let submitted = false;
    await page.route(source === "upload" ? "**/api/v1/jobs" : "**/api/v1/youtube-jobs", async (route) => {
      if (source === "upload") {
        const body = route.request().postData()!;
        expect(body).toContain('name="skip_seconds"\r\n\r\n19');
      } else expect(route.request().postDataJSON().skip_seconds).toBe(19);
      submitted = true;
      await route.fulfill({ json: { id: "skipped", status: "queued", progress: 0, artifacts: [], message: "Queued" } });
    });
    await page.route("**/api/v1/jobs/skipped", (route) => route.fulfill({ json: { id: "skipped", status: "queued", progress: 0, artifacts: [], message: "Queued" } }));
    await page.goto("/");
    await expect(page.getByLabel("Skip opening seconds")).toHaveValue("0");
    if (source === "upload") await page.locator('input[type="file"]').setInputFiles({ name: "mv.wav", mimeType: "audio/wav", buffer: Buffer.from("test") });
    else await page.getByLabel("YouTube video URL").fill("https://www.youtube.com/watch?v=abcdefghijk");
    await page.getByLabel("Skip opening seconds").fill("19");
    await page.getByRole("button", { name: "Start analysis", exact: true }).click();
    await expect.poll(() => submitted).toBe(true);
  });
}

test("rejects negative skip before sending an upload", async ({ page }) => {
  let submitted = false;
  await page.route("**/api/v1/jobs", (route) => { submitted = true; return route.abort(); });
  await page.goto("/");
  await page.locator('input[type="file"]').setInputFiles({ name: "mv.wav", mimeType: "audio/wav", buffer: Buffer.from("test") });
  await page.getByLabel("Skip opening seconds").fill("-1");
  await page.getByRole("button", { name: "Start analysis", exact: true }).click();
  expect(await page.getByLabel("Skip opening seconds").evaluate((input: HTMLInputElement) => input.validity.valid)).toBe(false);
  expect(submitted).toBe(false);
});

test('after YouTube refuses download selecting an audio file switches source and the new score can be saved and reopened',async({page})=>{
 const {readFileSync}=await import('node:fs');
 const score=JSON.parse(readFileSync(new URL('../../backend/examples/little-hands.json',import.meta.url),'utf8'));
 score.song={...score.song,title:'音檔替代測試',source_type:'local',source_url:null};
 let youtubeCalls=0,uploads=0,saved:any=null;
 await page.route('**/api/v1/youtube-jobs',r=>{youtubeCalls++;return r.fulfill({status:502,json:{detail:'YouTube 要求機器人驗證。請改用你有權使用的音檔上傳。'}});});
 const job={id:'upload-fallback',status:'completed',progress:100,artifacts:[],score};
 await page.route('**/api/v1/jobs',r=>{uploads++;expect(r.request().postData()).toContain('fallback.wav');return r.fulfill({json:{...job,status:'queued',score:null}});});
 await page.route('**/api/v1/jobs/upload-fallback',r=>r.fulfill({json:job}));
 await page.route('**/revisions',r=>{if(r.request().method()!=='POST')return r.fulfill({json:[]});saved=r.request().postDataJSON().score;return r.fulfill({json:{revision_id:'fallback-saved'}});});
 await page.route('**/revisions/fallback-saved',r=>r.fulfill({json:saved}));
 await page.goto('/');await page.getByLabel('YouTube video URL').fill('https://youtu.be/abcdefghijk');
 await page.getByRole('button',{name:'Start analysis',exact:true}).click();await expect(page.getByRole('alert')).toContainText('機器人驗證');
 await page.locator('input[type=file][accept*=".wav"]').setInputFiles({name:'fallback.wav',mimeType:'audio/wav',buffer:Buffer.from('fixture upload')});
 await expect(page.getByLabel('YouTube video URL')).toHaveValue('');
 await page.getByRole('button',{name:'Start analysis',exact:true}).click();
 await expect(page.getByRole('heading',{name:'音檔替代測試',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'保存目前工作版本',exact:true}).click();
 await expect.poll(()=>new URL(page.url()).searchParams.get('revision')).toBe('fallback-saved');
 expect(uploads).toBe(1);expect(youtubeCalls).toBe(1);expect(saved.song.title).toBe('音檔替代測試');
 await page.reload();await expect(page.getByRole('heading',{name:'音檔替代測試',exact:true})).toBeVisible();
});
