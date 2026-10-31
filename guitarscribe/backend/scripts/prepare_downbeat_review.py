"""Prepare a fixed, unsaved downbeat-only review from a passed decoder comparison.

Usage: python prepare_downbeat_review.py DECODER_REPORT PREPARED_SCORE SOURCE_WAV OUTPUT_DIR
The excerpt is frozen to 24–64s; no harmonic boundary/label changes are allowed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models.analysis import BeatInfo, RhythmSuggestion
from app.models.score import SongScore
from app.exporters.midi import compile_playback_manifest
from app.services.downbeat_rhythm import PATTERN_ID


def prepare(report_path, score_path, source, output):
    report = json.loads(report_path.read_text())
    assert report['baseline_exact_parity']
    result = report['decoders']['dbn']
    assert result['structural_gate'] == 'passed'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == report['source_sha256']
    original = SongScore.model_validate_json(score_path.read_text())
    candidate = original.model_copy(deep=True)
    projection = result['projection']
    candidate.analysis.timing_status = 'metered'
    candidate.analysis.bpm = projection['bpm']
    candidate.analysis.time_signature = projection['time_signature']
    candidate.analysis.warnings.append('離線拍格候選，尚未取得人耳確認；不是正式分析或原始譜。')
    candidate.beats = [BeatInfo.model_validate(b) for b in projection['beats']]
    meter = int(projection['time_signature'][0])
    candidate.rhythm = RhythmSuggestion(pattern_id=PATTERN_ID, label='每小節一下', subdivision=4,
                                       display=['D'] + [None] * (meter - 1), accents=[1] + [0] * (meter - 1))
    candidate.provenance.parameters.update(downbeat_review='2026-10-31', downbeat_musical_verdict='unconfirmed',
                                           beat_this_dbn=True, analysis_source_job_id=report['job'])
    assert candidate.chords == original.chords and candidate.melody == original.melody
    manifest = compile_playback_manifest(candidate)
    start, end = 24, 64
    attacks = [e for e in manifest.events if e.track == 'guitar']
    expected = [b.time for b in candidate.beats if b.beat == 1 and start <= b.time < end]
    actual = [e.start for e in attacks if start <= e.start < end]
    assert actual == expected, 'Every downbeat in this excerpt must have playable harmony'
    assert all(e.start < e.end <= candidate.song.duration_seconds for e in attacks)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'score.json').write_text(candidate.model_dump_json(indent=2))
    (output / 'manifest.json').write_text(manifest.model_dump_json(indent=2))
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(source), '-af',
                    f'atrim=start={start}:end={end},asetpts=PTS-STARTPTS', '-ar', '22050', '-ac', '1',
                    '-c:a', 'pcm_f32le', str(output / 'source.wav')], check=True)
    packet = dict(title='第一組：刷奏跟著小節', start=start, end=end, job=report['job'],
                  harmony_unchanged=True, clip_downbeats=expected, clip_strums=actual,
                  musical_verdict='unconfirmed', source_sha256=report['source_sha256'],
                  score_sha256=hashlib.sha256(candidate.model_dump_json().encode()).hexdigest(),
                  manifest_sha256=hashlib.sha256(manifest.model_dump_json().encode()).hexdigest())
    (output / 'packet.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2))
    print(json.dumps(packet, ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    for name in ('report','score','source','output'): parser.add_argument(name,type=Path)
    args=parser.parse_args();prepare(args.report,args.score,args.source,args.output)
