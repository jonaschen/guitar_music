"""Read-only cross-song inventory; no analysis reruns or parameter selection.

Usage: python audit_song_batch.py OUTPUT_DIR WORK_DIR [WORK_DIR ...]
Includes failed attempts. Historical human verdicts remain in their reports.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models.score import SongScore
from app.services.analysis_health import build_analysis_health, POLICY


def audit(works, output):
    rows = []
    for work in works:
        db = sqlite3.connect(f'file:{work / "jobs/jobs.sqlite3"}?mode=ro', uri=True)
        with db:
            payloads = db.execute('SELECT id,payload FROM jobs ORDER BY rowid').fetchall()
        for job_id, payload in payloads:
            job = json.loads(payload)
            row = dict(workspace=str(work), job=job_id, status=job['status'],
                       source_url=job.get('source_url'), created_at=job['created_at'],
                       skip_seconds=job.get('skip_seconds'), analysis_seconds=job.get('analysis_seconds'),
                       payload_sha256=hashlib.sha256(payload.encode()).hexdigest(),
                       error=job.get('error'), title=(job.get('score') or {}).get('song', {}).get('title'))
            if job['status'] == 'completed' and job.get('score'):
                path=work/'jobs'/job_id/'timing-rejection.json'
                evidence=json.loads(path.read_text()) if path.exists() else None
                row['health']=build_analysis_health(SongScore.model_validate(job['score']),evidence)
            rows.append(row)
        # Fail if a concurrent job update prevents an internally frozen report.
        assert payloads == db.execute('SELECT id,payload FROM jobs ORDER BY rowid').fetchall(), 'Jobs changed during audit; retry when idle'
        db.close()
    output.mkdir(parents=True, exist_ok=False)
    (output/'report.json').write_text(json.dumps(dict(policy=POLICY, rows=rows),ensure_ascii=False,indent=2,allow_nan=False))
    lines=['# Codex：跨歌曲固定規則盤點', '',
           '唯讀既有資料，不重跑辨識、不調參。歷史人耳判決保留於原紀錄；數字不是準確率。重複來源／裁切片段不算獨立歌曲。', '',
           '| 工作 | 標題 | 秒數 | 拍格 | 密度切換提示 | 和弦 | <1秒 | 刷奏 |',
           '|---|---|---:|---|---:|---:|---:|---:|']
    for row in rows:
        h=row.get('health');title=str(row.get('title') or row['source_url'] or '未命名').replace('|','／').replace('\n',' ')
        if h:
            c=h['chords'];p=h['playback']
            lines.append(f"| {row['job']} | {title} | {h['duration_seconds']:.1f} | {h['timing_status']} | {len(h['pulse_density']['octave_density_changes'])} | {c['count']} | {c['under_one_second']} | {p.get('guitar_events','錯誤')} |")
        else:
            lines.append(f"| {row['job']} | {title} | — | {row['status']} | — | — | — | — |")
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(attempts=len(rows),completed=sum('health' in r for r in rows),output=str(output))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('work',type=Path,nargs='+')
    a=p.parse_args();audit(a.work,a.output)
