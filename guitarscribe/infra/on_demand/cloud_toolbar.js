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
  const maintenance = document.createElement('details');
  const maintenanceTitle = document.createElement('summary'); maintenanceTitle.textContent = '保存與備份';
  const backupState = document.createElement('span'); backupState.setAttribute('aria-label', '雲端備份狀態');
  backupState.setAttribute('role','status'); backupState.textContent = '正在查詢備份…';
  const backupInfo = document.createElement('p');
  const distinction = document.createElement('p'); distinction.textContent = '「已保存」表示進度已寫入主機；備份會另外定期保存到私人儲存空間，分析中可能延後。';
  maintenance.append(maintenanceTitle, backupInfo, distinction);
  maintenance.style.cssText = 'max-width:100%;flex-basis:100%';
  bar.append(menu, clock, control, backupState, maintenance); document.body.prepend(bar);
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
  async function updateBackup() {
    try {
      const response = await fetch('/backend/cloud/maintenance', {cache:'no-store'});
      if (!response.ok) throw Error();
      const data = await response.json(), backup = data.backup || {};
      const labels = {complete:'已完成備份',pending:'新修改等待備份',running:'正在備份',
        deferred:'備份延後，等待下一輪',failed:'備份失敗，已保存的進度仍在主機',
        interrupted:'上次備份中斷，等待下一輪',unknown:'尚無可確認的備份紀錄'};
      backupState.textContent = labels[backup.state] || labels.unknown;
      if (data.disk_low) backupState.textContent += ' · 主機空間不足，請檢查使用狀態';
      const stamp = Number(backup.last_success_at);
      backupInfo.textContent = Number.isFinite(stamp) && stamp > 0 ?
        '最近完成備份：' + new Date(stamp*1000).toLocaleString('zh-TW') + '。完成時間不表示之後的修改已備份。' :
        '尚未取得完成時間；不代表練習稿未保存。';
    } catch {
      backupState.textContent = '備份狀態暫時無法確認';
      backupInfo.textContent = '請保留目前頁面的草稿，稍後會再次查詢。';
    }
  }
  let updating = false;
  async function update() {
    if (document.visibilityState !== 'visible' || updating) return;
    updating = true;
    try {
      const r = await fetch('/cloud/status', {cache:'no-store'}); if (!r.ok) return;
      const state = await r.json();
      if (state.stop_at) {
        const minutes = Math.max(0, Math.floor((state.stop_at * 1000 - Date.now()) / 60000));
        clock.textContent = minutes < 15 ? `本輪剩 ${minutes} 分鐘，請確認已保存` : `本輪剩約 ${minutes} 分鐘`;
      } else clock.textContent = '雲端主機已休息，可從使用狀態重新啟動';
      if (state.state === 'running') {
        await Promise.all([updateBackup(), fetch('/backend/cloud/activity', {
          method:'POST', headers:{'X-GuitarScribe-Activity':'visible'}, cache:'no-store'
        })]);
      } else backupState.textContent = '主機休息中，啟動後可查備份狀態';
    } catch { clock.textContent = '連線暫時中斷，請保留目前頁面的草稿'; }
    finally { updating = false; }
  }
  update(); setInterval(update, 60000);
  document.addEventListener('visibilitychange', update);
})();
