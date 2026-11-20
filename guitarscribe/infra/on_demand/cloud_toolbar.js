/* Personal cloud navigation. The original React practice UI stays intact. */
(() => {
  const bar = document.createElement('aside');
  bar.setAttribute('aria-label', '雲端練習');
  bar.style.cssText = 'display:flex;flex-wrap:wrap;align-items:center;gap:12px;padding:10px 18px;background:#edf3f1;color:#233d35;font:14px system-ui;border-bottom:1px solid #cfddd6;position:relative;z-index:20';
  const menu = document.createElement('details');
  const summary = document.createElement('summary'); summary.textContent = '我的歌曲'; menu.append(summary);
  const list = document.createElement('div');
  list.style.cssText = 'position:absolute;left:12px;top:44px;background:white;padding:16px;border:1px solid #cfddd6;border-radius:8px;max-height:60vh;overflow:auto;width:min(520px,88vw);box-shadow:0 8px 24px #0002';
  list.textContent = '正在載入歌曲…'; menu.append(list);
  const clock = document.createElement('span'); clock.setAttribute('role', 'status'); clock.textContent = '個人雲端';
  const control = document.createElement('a'); control.href = '/cloud'; control.target = '_blank'; control.rel = 'noopener'; control.textContent = '使用狀態';
  bar.append(menu, clock, control); document.body.prepend(bar);
  fetch('/backend/cloud/library').then(r => { if (!r.ok) throw Error(); return r.json(); }).then(data => {
    list.replaceChildren();
    if (!data.songs.length) list.textContent = '尚無歌曲，可在原畫面加入。';
    for (const song of data.songs) {
      const row = document.createElement('div'); row.style.cssText = 'padding:10px 0;border-bottom:1px solid #eee';
      const title = document.createElement('div'); title.textContent = song.title;
      const visual = document.createElement('a'); visual.textContent = '視覺練習';
      visual.href = '/?' + new URLSearchParams({practice:'roots', visual:'1', job:song.job_id});
      const score = document.createElement('a'); score.textContent = '樂譜'; score.style.marginLeft = '20px';
      score.href = '/?' + new URLSearchParams(song.revision_id ? {revision:song.revision_id} : {job:song.job_id});
      // A new tab retains any unfinished draft in the original tab.
      for (const a of [visual, score]) { a.target = '_blank'; a.rel = 'noopener'; }
      row.append(title, visual, score); list.append(row);
    }
  }).catch(() => { list.textContent = '歌曲清單暫時無法載入，請重新整理；目前頁面可繼續使用。'; });
  async function update() {
    if (document.visibilityState !== 'visible') return;
    try {
      const r = await fetch('/cloud/status', {cache:'no-store'}); if (!r.ok) return;
      const state = await r.json();
      if (state.stop_at) {
        const minutes = Math.max(0, Math.floor((state.stop_at * 1000 - Date.now()) / 60000));
        clock.textContent = minutes < 15 ? `本輪剩 ${minutes} 分鐘，請確認已保存` : `本輪剩約 ${minutes} 分鐘`;
      } else clock.textContent = '雲端主機已休息，可從使用狀態重新啟動';
      if (state.state === 'running') await fetch('/backend/cloud/activity', {
        method:'POST', headers:{'X-GuitarScribe-Activity':'visible'}, cache:'no-store'
      });
    } catch { clock.textContent = '連線暫時中斷，請保留目前頁面的草稿'; }
  }
  update(); setInterval(update, 60000);
  document.addEventListener('visibilitychange', update);
})();
