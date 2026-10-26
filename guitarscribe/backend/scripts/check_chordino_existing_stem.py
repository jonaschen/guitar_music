"""Single frozen source ablation using the existing Chordino plugin, no tuning."""
import hashlib
import json
from pathlib import Path
import time

import librosa
import numpy as np
import soundfile as sf
import vamp

ROOT = Path(__file__).resolve().parents[2]
JOB = 'db79e1145ea046088b8aa5ef421d0e3f'
directory = ROOT/f'output/work/jobs/{JOB}'
output = ROOT/'output/evaluation/chordino-existing-stem-2026-10-26-verified'
output.mkdir(parents=True, exist_ok=False)


def write(name, data):
    (output/name).write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


raw = json.loads((directory/'chord-analysis.json').read_text())
library = Path(vamp.vampyhost.get_library_for('nnls-chroma:chordino'))
library_hash = hashlib.sha256(library.read_bytes()).hexdigest()
assert library_hash == raw['parameters']['chordino_library_sha256']
source = directory/'accompaniment-stem.wav'
sr = sf.info(directory/'analysis-source.wav').samplerate
assert sf.info(source).duration == sf.info(directory/'analysis-source.wav').duration
write('protocol.json', dict(job=JOB, input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
      library_sha256=library_hash, samplerate=sr, parameters='vamp.collect defaults, same as saved analyzer',
      hypothesis='Vocal contribution may create transient chord labels; change only input from original mix to already separated accompaniment',
      decision='Inspect all original intervals and preservation of retained labels. No automatic integration or quality claim. Stop after this one source run.'))
began = time.monotonic()
y, sr = librosa.load(source, sr=sr)
data = vamp.collect(y, sr, 'nnls-chroma:chordino')['list']
events = [dict(start=float(e['timestamp']),end=float(data[i+1]['timestamp']) if i+1<len(data) else len(y)/sr,symbol=e['label']) for i,e in enumerate(data)]
write('raw-events.json', events)
# The plugin may emit a terminal marker at/after audio duration. Preserve it
# in the raw output, but it is not an audible interval. Reject internal errors.
terminal_markers = [e for e in events if e['end'] <= e['start']]
assert all(e is events[-1] and e['start'] >= len(y)/sr for e in terminal_markers)
events = [e for e in events if e['end'] > e['start']]
accepted = json.loads((ROOT/'docs/diagnostics/2026-10-26/user-chord-omissions.json').read_text())
original = json.loads((ROOT/'docs/diagnostics/2026-10-26/frozen-chords.json').read_text())
rows=[]
for c in original['chords']:
    overlaps=[]
    midpoint=(c['start']+c['end'])/2
    target=next(e['symbol'] for e in accepted['chords'] if e['start']<=midpoint<e['end'])
    for event in events:
        duration=max(0,min(event['end'],10+c['end'])-max(event['start'],10+c['start']))
        if duration:overlaps.append(dict(symbol=event['symbol'],seconds=duration))
    rows.append(dict(**c,target=target,omitted=any(abs(e['start']-c['start'])<1e-8 for e in accepted['omitted']),
                     stem_overlaps=overlaps,target_overlap_seconds=sum(e['seconds'] for e in overlaps if e['symbol']==target)))
report=dict(seconds=time.monotonic()-began,events=events,rows=rows,terminal_markers=terminal_markers,
            caution='Agreement with human-guided accompaniment is not transcription accuracy; retained chords are not independent ground truth')
write('report.json',report)
packet = dict(job=JOB, window=[10,40], capo=0, method='Same Chordino defaults on existing accompaniment stem; raw labels/times, no human omission list applied',
              chords=[dict(start=max(10,e['start'])-10,end=min(40,e['end'])-10,symbol=e['symbol'])
                      for e in events if e['start']<40 and e['end']>10])
write('listening-chords.json',packet)
public=ROOT/'frontend/public/listening/stem-chords-2026-10-26'
public.mkdir(parents=True, exist_ok=True)
(public/'chords.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2)+'\n')
html=(ROOT/'frontend/scripts/frozen-chords.html').read_text()
html=html.replace('跟著拍點刷和弦','伴奏音軌自動辨識 · 跟奏確認')
html=html.replace('以下是原辨識和弦，尚未驗證。','這次和弦由相同辨識器讀取分離伴奏自動產生，沒有套用你指定的五段略過。')
html=html.replace('這次沒有改和弦名稱、切換時刻或音訊，也沒有加入合成吉他。畫面提示沿用原辨識時間，可能不在第一拍換和弦。','音檔與拍格不變；和弦及換奏時間改用伴奏音軌的自動辨識結果。請確認是否仍順、有沒有新錯誤；不用再評拍點。這次沒有加入合成吉他。')
(public/'index.html').write_text(html)
for r in rows: print(round(r['start'],2),r['symbol'],'omit' if r['omitted'] else 'keep','target',r['target'],r['stem_overlaps'])
print('seconds',report['seconds'])
