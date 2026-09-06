import pytest
from app.core.config import Settings, ChordEngine
from app.core.pipeline import create_pipeline
from app.models.audio import SourceRequest, SourceType

@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pipeline_e2e(sample_wav):
    settings = Settings(chord_engine=ChordEngine.CHROMAGRAM)
    pipeline = create_pipeline(settings)
    
    request = SourceRequest(
        source_type=SourceType.LOCAL,
        path=sample_wav,
        rights_confirmed=True
    )
    
    score = await pipeline.run(request, {"chord_complexity": "standard"})
    
    assert score.schema_version == "1.0"
    assert len(score.chords) > 0
    assert len(score.beats) > 0
    assert 60 <= score.analysis.bpm <= 200
    
    json_str = score.model_dump_json()
    assert isinstance(json_str, str)
    assert len(json_str) > 0

@pytest.mark.asyncio
async def test_pipeline_rejects_audio_over_duration_limit(tmp_path):
    from app.models.audio import AudioAsset, NormalizedAudio, SourceRequest, SourceType
    from app.core.pipeline import AnalysisPipeline

    class Source:
        async def fetch(self, request): return AudioAsset(path=tmp_path / "input.wav", source_type=SourceType.LOCAL)
    class Preprocessor:
        async def normalize(self, asset): return NormalizedAudio(path=tmp_path / "normalized.wav", duration_seconds=2.0)
    pipeline = AnalysisPipeline(Preprocessor(), None, None, None, None, None, None, None, Source(), max_duration_seconds=1)
    with pytest.raises(ValueError, match="duration exceeds"):
        await pipeline.run(SourceRequest(source_type=SourceType.LOCAL, path=tmp_path / "input.wav"), {})


@pytest.mark.asyncio
async def test_pipeline_falls_back_to_full_mix_when_vocal_separation_fails(tmp_path):
    from app.core.pipeline import AnalysisPipeline
    from app.models.analysis import BeatAnalysis, ChordAnalysis, MelodyAnalysis, MelodyMode, MelodyNote, RhythmSuggestion
    from app.models.audio import AudioAsset, NormalizedAudio
    from app.postprocess.melody import MelodyPostProcessor

    normalized = NormalizedAudio(path=tmp_path / "normalized.wav", duration_seconds=8.0)

    class Source:
        async def fetch(self, request):
            return AudioAsset(path=normalized.path, source_type=SourceType.LOCAL)

    class Preprocessor:
        async def normalize(self, asset):
            return normalized

    class BeatAnalyzer:
        async def analyze(self, audio):
            return BeatAnalysis(bpm=120.0)

    class ChordAnalyzer:
        async def analyze(self, audio, beats):
            return ChordAnalysis()

    class ChordPost:
        def process(self, chords, beats, complexity):
            return chords

    class Separator:
        async def separate(self, audio, mode):
            raise RuntimeError("model unavailable")

    class MelodyAnalyzer:
        async def analyze(self, audio, beats, mode):
            assert audio is normalized
            return MelodyAnalysis(
                mode=MelodyMode.VOCAL,
                notes=[MelodyNote(id="n", start=0.0, end=0.5, midi=60, note="C4", confidence=0.9)],
            )

    class Mapper:
        def map_notes(self, melody):
            return melody

    class Rhythm:
        def suggest(self, beats, chords):
            return RhythmSuggestion()

    pipeline = AnalysisPipeline(
        Preprocessor(), BeatAnalyzer(), ChordAnalyzer(), MelodyAnalyzer(), ChordPost(),
        MelodyPostProcessor(), Rhythm(), Mapper(), Source(), Separator(),
    )
    score = await pipeline.run(
        SourceRequest(source_type=SourceType.LOCAL, path=normalized.path),
        {"melody_mode": "vocal", "separate_vocals": True},
    )

    assert score.melody
    assert any("Vocal separation failed" in warning for warning in score.analysis.warnings)
    assert any("without source separation" in warning for warning in score.analysis.warnings)
