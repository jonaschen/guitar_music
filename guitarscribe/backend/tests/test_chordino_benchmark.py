import asyncio
import json

import pytest

from app.models.analysis import ChordAnalysis, ChordEvent
from scripts.benchmark_chordino_pilot import run, unknown_label_summary


def test_benchmark_records_all_missing_inputs_and_refuses_overwrite(tmp_path):
    protocol = tmp_path / 'protocol.json'
    protocol.write_text(json.dumps({'recordings': ['first', 'second']}))
    output = tmp_path / 'result'
    report = asyncio.run(run(tmp_path, protocol, output))
    assert report['status'] == 'failed'
    assert [r['recording_id'] for r in report['records']] == ['first', 'second']
    assert all(r['failure'] for r in report['records'])
    saved = (output / 'report.json').read_bytes()
    with pytest.raises(FileExistsError):
        asyncio.run(run(tmp_path, protocol, output))
    assert (output / 'report.json').read_bytes() == saved


def test_unknown_output_is_reported_without_reclassifying_valid_extensions():
    analysis = ChordAnalysis(chords=[
        ChordEvent(id='known', start=0, end=1, symbol='Bm7b5'),
        ChordEvent(id='unknown', start=1, end=4, symbol='Cunknown'),
    ])
    result = unknown_label_summary(analysis, 3)
    assert result['count'] == 1
    assert result['duration_seconds'] == 2
