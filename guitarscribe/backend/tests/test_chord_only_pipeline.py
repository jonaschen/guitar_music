import pytest
from app.core.pipeline import AnalysisPipeline
from app.models.analysis import BeatAnalysis, BeatInfo, ChordAnalysis, ChordEvent, RhythmSuggestion
from app.models.audio import AudioAsset, NormalizedAudio, SourceRequest, SourceType

@pytest.mark.asyncio
async def test_off_skips_all_melody_work_even_if_separation_requested(tmp_path):
    audio = NormalizedAudio(path=tmp_path / 'mix.wav', duration_seconds=2)
    class Source:
        async def fetch(self, request):
            return AudioAsset(path=audio.path, source_type=SourceType.LOCAL)
    class Preprocessor:
        async def normalize(self, asset): return audio
    class BeatAnalyzer:
        async def analyze(self, audio):
            return BeatAnalysis(bpm=120, beats=[BeatInfo(time=i*.5, beat=i+1, measure=1) for i in range(4)])
    class ChordAnalyzer:
        async def analyze(self, audio, beats):
            return ChordAnalysis(confidence=.8, chords=[ChordEvent(id='c', start=0, end=2, symbol='C')])
    class ChordPost:
        def process(self, chords, *args): return chords
    class Forbidden:
        def __getattr__(self, name):
            pytest.fail(f'Frozen melody dependency called: {name}')
    class Rhythm:
        def suggest(self, beats, chords): return RhythmSuggestion()
    frozen = Forbidden()
    pipeline = AnalysisPipeline(Preprocessor(), BeatAnalyzer(), ChordAnalyzer(), frozen, ChordPost(), frozen, Rhythm(), frozen, Source(), frozen)
    score=await pipeline.run(SourceRequest(source_type=SourceType.LOCAL, path=audio.path),
        {'melody_mode':'off','separate_vocals':True,'_artifact_directory':str(tmp_path)})
    assert score.melody == []
    assert len(score.chords)==1 and len(score.beats)==4
    assert score.analysis.confidence == .8
    assert score.provenance.melody_engine == 'disabled'
    assert score.provenance.parameters['melody_note_processing'] == 'disabled'
    assert not score.analysis.warnings
    assert {p.name for p in tmp_path.iterdir()} == {'timing-analysis.json','chord-analysis.json'}
