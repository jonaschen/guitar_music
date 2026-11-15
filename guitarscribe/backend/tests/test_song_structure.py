import math

import pytest

from app.evaluation.song_structure import normalize_sections, summarize_candidate, verify_source, render_review


def test_complete_song_keeps_names_times_and_marks_every_section_unreviewed():
    raw = [{'start': 0, 'end': 4, 'label': 'verse'}, {'start': 4, 'end': 8, 'label': 'chorus'}]
    result = normalize_sections(raw, 8)
    assert [(s['start'], s['end'], s['label']) for s in result] == [(0, 4, 'verse'), (4, 8, 'chorus')]
    assert all(s['review_status'] == 'unreviewed' for s in result)
    assert result[0]['display_label'] == '主歌'


def test_gaps_stay_unknown_and_model_edge_labels_are_not_intro_or_outro():
    raw = [{'start': .5, 'end': 2, 'label': 'start'}, {'start': 3, 'end': 7, 'label': 'end'}]
    result = normalize_sections(raw, 8)
    assert [(s['start'], s['end']) for s in result] == [(0, .5), (.5, 2), (2, 3), (3, 7), (7, 8)]
    assert [s['label'] for s in result] == ['unknown', 'start', 'unknown', 'end', 'unknown']
    assert not any(s['display_label'] in ['前奏', '尾奏'] for s in result)


@pytest.mark.parametrize('raw', [
    [], [{'start': 0, 'end': math.nan, 'label': 'verse'}],
    [{'start': -1, 'end': 2, 'label': 'verse'}],
    [{'start': 0, 'end': 8.2, 'label': 'verse'}],
    [{'start': 2, 'end': 2, 'label': 'verse'}],
    [{'start': 0, 'end': 5, 'label': 'verse'}, {'start': 4, 'end': 8, 'label': 'chorus'}],
    [{'start': 4, 'end': 8, 'label': 'chorus'}, {'start': 0, 'end': 4, 'label': 'verse'}],
    [{'start': 0, 'end': 8, 'label': 'made-up-label'}],
])
def test_invalid_model_output_is_rejected_instead_of_silently_fixed(raw):
    with pytest.raises(ValueError):
        normalize_sections(raw, 8)


def test_frame_rounding_is_bounded_and_raw_end_is_retained():
    result = normalize_sections([{'start': 0, 'end': 8.01, 'label': 'outro'}], 8)
    assert result[0]['end'] == 8
    assert result[0]['model_end'] == 8.01


def test_no_reference_never_reports_accuracy_or_semantic_quality_pass():
    result = summarize_candidate([{'start': 0, 'end': 8, 'label': 'chorus'}], 8)
    assert result['coverage'] == 1
    assert result['semantic_quality'] == 'not_evaluated'
    assert result['reference_status'] == 'not_annotated'
    assert result['ready_as_default'] is False
    assert 'accuracy' not in result


def test_source_hash_mismatch_fails_before_model_import(tmp_path):
    path = tmp_path / 'input.wav'
    path.write_bytes(b'changed source')
    with pytest.raises(ValueError, match='SHA-256'):
        verify_source(path, '0' * 64)


def test_bridge_instrumental_and_solo_are_not_collapsed_to_interlude():
    result = normalize_sections([{'start': i, 'end': i + 1, 'label': name}
                                 for i, name in enumerate(['bridge', 'inst', 'solo'])], 3)
    assert [s['display_label'] for s in result] == ['橋段', '器樂段（間奏候選）', '獨奏段（間奏候選）']


def test_review_escapes_script_breakout_and_never_embeds_credentials():
    html = render_review([{'title': '</script><script>alert(1)</script>', 'sections': []}])
    assert '</script><script>alert(1)</script>' not in html
    assert '\\u003c/script>' in html
    assert 'Authorization' not in html
    assert '尚未確認正確' in html


@pytest.mark.parametrize('fault', ['rate', 'channels', 'frames', 'missing', 'duration'])
def test_precomputed_stems_reject_wrong_model_frontend(tmp_path, fault):
    import numpy as np
    import soundfile as sf
    from app.evaluation.song_structure import validate_stems
    for name in ['bass', 'drums', 'other', 'vocals']:
        if fault == 'missing' and name == 'vocals':
            continue
        rate = 48000 if fault == 'rate' else 44100
        frames = 22050 if fault == 'frames' and name == 'bass' else rate
        channels = 1 if fault == 'channels' else 2
        sf.write(tmp_path / f'{name}.wav', np.zeros((frames, channels)), rate)
    with pytest.raises(ValueError):
        validate_stems(tmp_path, 2 if fault == 'duration' else 1)


def test_precomputed_stems_record_audio_hash_and_exact_format(tmp_path):
    import numpy as np
    import soundfile as sf
    from app.evaluation.song_structure import validate_stems
    for name in ['bass', 'drums', 'other', 'vocals']:
        sf.write(tmp_path / f'{name}.wav', np.zeros((44100, 2)), 44100)
    result = validate_stems(tmp_path, 1)
    assert set(result) == {'bass', 'drums', 'other', 'vocals'}
    assert all(s['frames'] == 44100 and s['sample_rate'] == 44100 and len(s['sha256']) == 64
               for s in result.values())


@pytest.mark.parametrize('status', ['running', 'failed', 'cancelled_invalid_preprocessing'])
def test_review_rejects_leftover_candidate_from_incomplete_run(tmp_path, status):
    import json
    from app.evaluation.song_structure import load_ready_candidate
    (tmp_path / 'manifest.json').write_text(json.dumps({'status': status}))
    (tmp_path / 'candidate.json').write_text('{}')
    with pytest.raises(ValueError, match='completed'):
        load_ready_candidate(tmp_path)


def test_review_only_uses_completed_candidate_bound_to_current_source(tmp_path):
    import hashlib
    import json
    from app.evaluation.song_structure import load_ready_candidate
    audio = tmp_path / 'input.wav'
    audio.write_bytes(b'original local audio')
    source = {'audio': str(audio), 'audio_sha256': hashlib.sha256(audio.read_bytes()).hexdigest(),
              'job': 'job-a', 'title': 'song', 'root_source': {'fingerprint': 'fingerprint', 'source_start': 0, 'duration': 8}}
    manifest = {'status': 'candidate_ready_unreviewed', 'source': source}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    candidate = summarize_candidate([{'start': 0, 'end': 8, 'label': 'chorus'}], 8)
    candidate.update(title='song', job='job-a', fingerprint='fingerprint', source_start=0, duration=8)
    path = tmp_path / 'candidate.json'
    path.write_text(json.dumps(candidate))
    assert load_ready_candidate(tmp_path) == candidate
    candidate['fingerprint'] = 'other recording'
    path.write_text(json.dumps(candidate))
    with pytest.raises(ValueError, match='source'):
        load_ready_candidate(tmp_path)
    candidate['fingerprint'] = 'fingerprint'
    path.write_text(json.dumps(candidate))
    audio.write_bytes(b'changed local audio')
    with pytest.raises(ValueError, match='SHA-256'):
        load_ready_candidate(tmp_path)


def test_review_accepts_only_bounded_source_duration_rounding(tmp_path):
    import hashlib
    import json
    from app.evaluation.song_structure import load_ready_candidate
    audio = tmp_path / 'audio.wav';audio.write_bytes(b'audio')
    source = dict(audio=str(audio), audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
                  title='song', job='job-a', root_source=dict(fingerprint='f', source_start=0, duration=8.00001))
    (tmp_path / 'manifest.json').write_text(json.dumps(dict(status='candidate_ready_unreviewed', source=source)))
    candidate = summarize_candidate([dict(start=0, end=8, label='verse')], 8)
    candidate.update(title='song', job='job-a', fingerprint='f', source_start=0, duration=8)
    (tmp_path / 'candidate.json').write_text(json.dumps(candidate))
    assert load_ready_candidate(tmp_path)['duration'] == 8
    candidate['duration'] = 8.1
    (tmp_path / 'candidate.json').write_text(json.dumps(candidate))
    with pytest.raises(ValueError, match='source'):
        load_ready_candidate(tmp_path)


@pytest.mark.parametrize('end', [7, 8.01])
def test_review_rejects_noncanonical_candidate_intervals(tmp_path, end):
    import hashlib
    import json
    from app.evaluation.song_structure import load_ready_candidate
    audio = tmp_path / 'audio.wav';audio.write_bytes(b'audio')
    source = dict(audio=str(audio), audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
                  title='song', job='job-a', root_source=dict(fingerprint='f', source_start=0, duration=8))
    (tmp_path / 'manifest.json').write_text(json.dumps(dict(status='candidate_ready_unreviewed', source=source)))
    candidate = summarize_candidate([dict(start=0, end=8, label='verse')], 8)
    candidate.update(title='song', job='job-a', fingerprint='f', source_start=0, duration=8)
    candidate['sections'][0]['end'] = end
    (tmp_path / 'candidate.json').write_text(json.dumps(candidate))
    with pytest.raises(ValueError, match='canonical'):
        load_ready_candidate(tmp_path)
