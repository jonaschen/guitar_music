"""Opt-in chord candidate from an existing stem; never persists or edits sources."""
import hashlib
import math
from pathlib import Path

from ..models.analysis import ChordEvent
from ..models.score import SongScore
from .playable_chords import with_default_voicings


def build_candidate(score: SongScore, events: list[dict], provenance: dict) -> SongScore:
    if any(c.edited for c in score.chords):
        raise ValueError('Preserve manual chord edits; use the original chords for this candidate')
    if score.key_context.transpose_semitones or score.analysis.capo or score.guitar.capo:
        raise ValueError('This experimental candidate requires an untransposed Capo 0 score')
    if score.guitar.tuning != [40,45,50,55,59,64]:
        raise ValueError('This experimental candidate requires standard guitar tuning')
    duration = score.song.duration_seconds
    chords = []
    previous_end = 0.
    for i, event in enumerate(events):
        start, end = float(event['start']), float(event['end'])
        if not all(math.isfinite(t) for t in (start, end)) or start < 0:
            raise ValueError('Invalid chord timing')
        # Chordino may emit a final N marker beyond the end of its input.
        if i == len(events)-1 and event['symbol'] == 'N' and start >= duration and end == duration:
            continue
        if end <= start or start < previous_end-1e-8 or start >= duration:
            raise ValueError('Invalid or overlapping chord intervals')
        if end > duration and not (i+1 == len(events)-1 and events[-1]['symbol'] == 'N' and events[-1]['start'] == end):
            raise ValueError('Chord exceeds source duration')
        end = min(end, duration)
        previous_end = end
        if event['symbol'] == 'N':
            continue  # Preserve silence as a gap, never extend a preceding chord.
        chords.append(ChordEvent(id=f'stem-chord-{i}', start=start, end=end, symbol=event['symbol'],
                                 confidence=0, needs_review=True, review_reasons=['uncalibrated_stem_candidate']))
    if not chords:
        raise ValueError('No pitched chords found in existing accompaniment')
    candidate = score.model_copy(deep=True)
    candidate.chords = chords
    candidate = with_default_voicings(candidate)
    if any(not c.available_voicings for c in candidate.chords):
        raise ValueError('Candidate contains a chord with no playable voicing; original score retained')
    for chord in candidate.chords:
        selected = next(v for v in chord.available_voicings if v.id == chord.voicing_id)
        pcs = {(t+f)%12 for t,f in zip(candidate.guitar.tuning, selected.frets) if f is not None}
        if len(pcs) < 3:
            raise ValueError(f'Incomplete guitar voicing for {chord.symbol}; original score retained')
    candidate.provenance.parameters.update(provenance)
    candidate.provenance.parameters['chord_input_source'] = 'existing-accompaniment-stem-v1'
    candidate.provenance.parameters['chord_candidate'] = True
    candidate.provenance.chord_engine = 'chordino'
    candidate.analysis.warnings.append('Experimental accompaniment-stem chord candidate. Beats, melody and key are retained; chord confidence is uncalibrated. Review before saving a new revision.')
    return candidate


def analyze_existing_stem(score: SongScore, directory: Path, job_id: str) -> SongScore:
    import soundfile as sf
    import librosa
    import vamp
    stem = directory/'accompaniment-stem.wav'
    source = directory/'analysis-source.wav'
    stem_info, source_info = sf.info(stem), sf.info(source)
    if abs(stem_info.duration-source_info.duration) > 1/source_info.samplerate or abs(source_info.duration-score.song.duration_seconds) > 1/source_info.samplerate:
        raise ValueError('Saved accompaniment and score timelines differ')
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    stem_hash = hashlib.sha256(stem.read_bytes()).hexdigest()
    audio, sr = librosa.load(stem, sr=source_info.samplerate)
    raw = vamp.collect(audio, sr, 'nnls-chroma:chordino')['list']
    events = [dict(start=float(e['timestamp']), end=float(raw[i+1]['timestamp']) if i+1<len(raw) else score.song.duration_seconds,
                   symbol=e['label']) for i,e in enumerate(raw)]
    library = Path(vamp.vampyhost.get_library_for('nnls-chroma:chordino'))
    return build_candidate(score, events, dict(chord_candidate_source_job_id=job_id, analysis_source_job_id=job_id,
        chord_source_audio_sha256=source_hash, chord_accompaniment_sha256=stem_hash,
        chordino_library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
        chord_candidate_sample_rate=sr, chord_candidate_parameters='vamp.collect defaults'))
