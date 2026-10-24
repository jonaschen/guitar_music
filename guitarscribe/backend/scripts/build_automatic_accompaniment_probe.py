"""Build a guitar-only listening probe with fixed engines and no manual timing recipe."""
import argparse
import asyncio
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import time

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.beats.learned_projection import project_learned_beats
from app.analyzers.chords.chordino import ChordinoChordAnalyzer
from app.exporters.midi import compile_playback_manifest
from app.models.audio import NormalizedAudio
from app.models.score import AnalysisSummary, SongInfo, SongScore
from app.services.playable_chords import with_default_voicings


async def run(packet: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads((packet / 'config.json').read_text())
    source = packet / 'audio.wav'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != config['audio_sha256']:
        raise ValueError('Packet audio hash mismatch')
    saved = SongScore.model_validate_json((packet / 'score.json').read_text())
    if saved.analysis.capo or saved.key_context.transpose_semitones:
        raise ValueError('This probe currently requires untransposed, capo-zero playback')
    info = sf.info(source)
    duration = float(config['content_duration'])
    if not 0 < duration <= info.duration:
        raise ValueError('Invalid packet content duration')

    import torch
    from beat_this.inference import File2Beats
    torch.set_num_threads(2)
    started = time.perf_counter()
    predictor = File2Beats(checkpoint_path='small0', device='cpu', dbn=False)
    raw_beats, raw_downbeats = predictor(str(source))
    # Trim only the packet's predeclared rendering tail, never musical errors.
    beat_times = [float(t) for t in raw_beats if t < duration]
    downbeat_times = [float(t) for t in raw_downbeats if t < duration]
    (output / 'raw-timing.json').write_text(json.dumps({
        'beats': raw_beats.tolist(), 'downbeats': raw_downbeats.tolist()}, indent=2))
    beats = project_learned_beats(beat_times, downbeat_times, version('beat-this'))
    audio = NormalizedAudio(path=source, sample_rate=44100, channels=info.channels,
                            duration_seconds=info.duration)
    chords = await ChordinoChordAnalyzer().analyze(audio, beats)
    (output / 'chord-analysis.json').write_text(chords.model_dump_json(indent=2))
    events = [c.model_copy(update={'end': min(c.end, duration)})
              for c in chords.chords if c.start < duration]
    score = with_default_voicings(SongScore(
        song=SongInfo(title='Automatic accompaniment probe', duration_seconds=duration),
        analysis=AnalysisSummary(bpm=beats.bpm, time_signature=beats.time_signature),
        beats=beats.beats, chords=events, rhythm=saved.rhythm.model_copy(deep=True),
        guitar=saved.guitar.model_copy(deep=True)))
    unsupported = [c.symbol for c in score.chords if not c.available_voicings
                   or c.available_voicings[0].id.startswith('root-note-')]
    if unsupported:
        raise ValueError(f'Cannot render faithful chord voicings: {unsupported}')
    manifest = compile_playback_manifest(score)
    if not any(e.track == 'guitar' for e in manifest.events):
        raise ValueError('No guitar events compiled')
    (output / 'score.json').write_text(score.model_dump_json(indent=2))
    (output / 'manifest.json').write_text(manifest.model_dump_json(indent=2))
    (output / 'report.json').write_text(json.dumps({
        'source_sha256': source_hash, 'source_config_id': config['config_id'],
        'duration_seconds': duration, 'analysis_offset': config['analysis_start'],
        'manual_timing_or_chord_edits': 0, 'saved_revision_written': False,
        'beat_model': 'small0', 'device': 'cpu', 'threads': 2, 'dbn': False,
        'beat_this_version': version('beat-this'), 'vamp_version': version('vamp'),
        'beat_weights_sha256': hashlib.sha256((Path(torch.hub.get_dir()) /
            'checkpoints/beat_this-small0.ckpt').read_bytes()).hexdigest(),
        'chord_engine': 'Chordino built-in defaults; no external chord dictionary',
        'rhythm': saved.rhythm.model_dump(mode='json'),
        'wall_seconds': time.perf_counter() - started,
        'scope': 'Guitar-only candidate on original mixed audio; no new melody extraction. Listening experiment, not quality acceptance.',
    }, indent=2))
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.packet, args.output))
