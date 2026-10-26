"""Lock the guitar schedule from the independently rendered listening baseline.

This detects regressions, not musical correctness. Human review covered 10–40s.
"""
import json
from pathlib import Path

import pytest

from app.models.score import SongScore
from app.services.chord_entry_performance import build_entry_performance


@pytest.mark.parametrize('mode',['original','continuous'])
def test_reviewed_live_acoustic_schedule(mode):
    fixture=json.loads((Path(__file__).parent/'fixtures/reviewed_live_chord_entry.json').read_text())
    score=SongScore.model_validate(fixture['score'])
    original,candidate,_,_=build_entry_performance(score,'continuous')
    manifest=original if mode=='original' else candidate
    start,end=fixture['window']
    keys=['start','sustain_end','pitches','pitch_offsets','pitch_velocities','velocity','stroke','source_id']
    actual=[{k:e.get(k) for k in keys} for e in manifest.model_dump(mode='json')['events']
            if e['track']=='guitar' and e['start']<end and (e.get('sustain_end') or e['end'])>start]
    assert actual==fixture[mode]
