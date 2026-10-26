"""Build an explicit user-guided diagnostic, never a duration-based filter."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
evidence = ROOT / 'docs/diagnostics/2026-10-26'
original = json.loads((evidence / 'frozen-chords.json').read_text())
# Exact original event identities matched to the user's displayed times/symbols.
omissions = {1: (4.16, 'F'), 6: (12.76, 'C'), 7: (13.50, 'F6'),
             12: (21.35, 'Em'), 13: (21.95, 'F/G')}
candidate = copy.deepcopy(original)
candidate['method'] = 'User-named five events omitted; preceding chord held through each omitted interval. No global duration rule, snapping, or audio modification.'
candidate['status'] = 'User found omission smoother; preceding-chord extension is an explicit implementation assumption, not verified harmonic truth'
candidate['omitted'] = []
events = []
for i, event in enumerate(original['chords']):
    if i in omissions:
        time, symbol = omissions[i]
        assert round(event['start'], 2) == time and event['symbol'] == symbol
        candidate['omitted'].append(copy.deepcopy(event))
        events[-1]['end'] = event['end']
    elif events and events[-1]['symbol'] == event['symbol']:
        assert abs(events[-1]['end'] - event['start']) < 1e-8
        events[-1]['end'] = event['end']
    else:
        events.append(copy.deepcopy(event))
candidate['chords'] = events
assert len(events) == 12 and events[0]['start'] == 0 and events[-1]['end'] == 30
assert all(a['end'] == b['start'] for a, b in zip(events, events[1:]))
assert events[-1] == original['chords'][-1]  # Short clip-truncated final Em is preserved.
for a, b in zip(sorted({0., 30., *[e['start'] for e in original['chords']], *[e['end'] for e in original['chords']]}),
                sorted({0., 30., *[e['start'] for e in original['chords']], *[e['end'] for e in original['chords']]})[1:]):
    t = (a+b)/2
    old = next(e for e in original['chords'] if e['start'] <= t < e['end'])
    new = next(e for e in events if e['start'] <= t < e['end'])
    if not any(e['start'] <= t < e['end'] for e in candidate['omitted']):
        assert old['symbol'] == new['symbol']
serialized = json.dumps(candidate, ensure_ascii=False, indent=2) + '\n'
(evidence / 'user-chord-omissions.json').write_text(serialized)
public = ROOT / 'frontend/public/listening/user-chord-omissions-2026-10-26'
public.mkdir(parents=True, exist_ok=True)
(public / 'chords.json').write_text(serialized)
html = (ROOT / 'frontend/scripts/frozen-chords.html').read_text()
html = html.replace('跟著拍點刷和弦', '跳過你指出的五段和弦')
html = html.replace('以下是原辨識和弦，尚未驗證。', '只跳過你指出的五段，前一和弦持續到下一個保留和弦。')
html = html.replace('這次沒有改和弦名稱、切換時刻或音訊，也沒有加入合成吉他。畫面提示沿用原辨識時間，可能不在第一拍換和弦。', '音訊與拍格完全相同。只處理你指定的五段；其餘和弦及入口維持原樣，沒有加入合成吉他。這是人工指定的診斷版本，尚不是自動修正。')
(public / 'index.html').write_text(html)
print('12 displayed intervals; only five named intervals changed; final short Em retained')
