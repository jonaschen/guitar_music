from pathlib import Path

import pytest

from app.analyzers.beats.beat_this_adapter import BeatThisBeatAnalyzer
from app.core.config import BeatEngine, ChordEngine, Settings
from app.core.pipeline import create_pipeline
from app.exporters.midi import compile_playback_manifest
from app.models.analysis import ChordAnalysis, ChordEvent, MelodyAnalysis
from app.models.audio import SourceRequest, SourceType
from app.services.revisions import RevisionStore


@pytest.mark.asyncio
async def test_new_engine_events_and_extended_voicings_survive_pipeline_and_reload(sample_wav, tmp_path):
    patterns = Path(__file__).resolve().parents[2] / 'rhythm-patterns'
    pipeline = create_pipeline(Settings(beat_engine=BeatEngine.BEAT_THIS_SMALL,
        chord_engine=ChordEngine.CHROMAGRAM, rhythm_patterns_dir=patterns))
    pipeline.beat_analyzer = BeatThisBeatAnalyzer(predictor=lambda _: (
        [i * .5 for i in range(16)], [0, 2, 4, 6]))
    source_chords = [ChordEvent(id='g6', start=.23, end=3.73, symbol='G6'),
                     ChordEvent(id='d7', start=3.73, end=8, symbol='D7')]

    class Chords:
        async def analyze(self, *_):
            return ChordAnalysis(chords=source_chords, engine='chordino')

    class Melody:
        async def analyze(self, *_):
            return MelodyAnalysis()

    pipeline.chord_analyzer = Chords()
    pipeline.melody_analyzer = Melody()
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    score = await pipeline.run(SourceRequest(source_type=SourceType.LOCAL, path=sample_wav,
        rights_confirmed=True), {'chord_complexity': 'full', '_artifact_directory': str(artifacts)})
    assert [(c.symbol, c.start, c.end) for c in score.chords] == [('G6', .23, 3.73), ('D7', 3.73, 8)]
    assert score.rhythm.pattern_id == 'pop_4_4_8th_01'
    assert score.rhythm.accents == [1, 0, .7, .4, 0, .5, .8, .4]
    assert all(not c.available_voicings[0].id.startswith('root-note') for c in score.chords)
    manifest = compile_playback_manifest(score)
    assert all(len(e.pitches) >= 4 for e in manifest.events if e.track == 'guitar')
    store = RevisionStore(tmp_path / 'revisions')
    revision = store.save(score)
    assert compile_playback_manifest(store.load(revision)) == manifest
    assert (artifacts / 'chord-analysis.json').is_file()
