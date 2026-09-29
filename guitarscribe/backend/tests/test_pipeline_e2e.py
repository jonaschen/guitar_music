import pytest
from app.core.config import Settings, ChordEngine
from app.core.pipeline import create_pipeline
from app.models.audio import SourceRequest, SourceType
from app.models.candidates import ChordResult

@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pipeline_e2e(sample_wav, tmp_path):
    settings = Settings(chord_engine=ChordEngine.CHROMAGRAM)
    pipeline = create_pipeline(settings)
    
    request = SourceRequest(
        source_type=SourceType.LOCAL,
        path=sample_wav,
        rights_confirmed=True
    )
    
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    score = await pipeline.run(
        request,
        {"chord_complexity": "standard", "_artifact_directory": str(artifacts)},
    )
    
    assert score.schema_version == "1.0"
    assert score.provenance.tempo_map_version == "legacy-beat-grid-v1"
    assert score.provenance.parameters["melody_mode"] == "vocal"
    assert score.provenance.parameters["decoder_change_threshold"] == 0.12
    assert len(score.chords) > 0
    assert all(chord.available_voicings and chord.voicing_id for chord in score.chords)
    assert len(score.beats) > 0
    assert 60 <= score.analysis.bpm <= 200
    assert (artifacts / "timing-candidates.json").is_file()
    assert (artifacts / "chord-candidates.json").is_file()
    chord_artifact = ChordResult.model_validate_json((artifacts / "chord-candidates.json").read_text())
    assert chord_artifact.regions
    assert all(region.label_candidates for region in chord_artifact.regions)
    
    json_str = score.model_dump_json()
    assert isinstance(json_str, str)
    assert len(json_str) > 0

@pytest.mark.asyncio
async def test_pipeline_rejects_audio_over_duration_limit(tmp_path):
    from app.models.audio import AudioAsset, NormalizedAudio, SourceRequest, SourceType
    from app.core.pipeline import AnalysisPipeline

    class Source:
        async def fetch(self, request): return AudioAsset(path=tmp_path / "input.wav", source_type=SourceType.LOCAL)
    workspace = tmp_path / "guitarscribe_duration_limit"
    workspace.mkdir()
    class Preprocessor:
        async def normalize(self, asset): return NormalizedAudio(path=workspace / "normalized.wav", duration_seconds=2.0, temporary_directory=workspace)
    pipeline = AnalysisPipeline(Preprocessor(), None, None, None, None, None, None, None, Source(), max_duration_seconds=1)
    with pytest.raises(ValueError, match="duration exceeds"):
        await pipeline.run(SourceRequest(source_type=SourceType.LOCAL, path=tmp_path / "input.wav"), {})
    assert not workspace.exists()


@pytest.mark.asyncio
async def test_pipeline_falls_back_to_full_mix_when_vocal_separation_fails(tmp_path):
    from app.core.pipeline import AnalysisPipeline
    from app.models.analysis import BeatAnalysis, ChordAnalysis, MelodyAnalysis, MelodyMode, MelodyNote, RhythmSuggestion
    from app.models.audio import AudioAsset, NormalizedAudio
    from app.postprocess.melody import MelodyPostProcessor

    workspace = tmp_path / "guitarscribe_successful_pipeline"
    workspace.mkdir()
    normalized = NormalizedAudio(path=workspace / "normalized.wav", duration_seconds=8.0, temporary_directory=workspace)

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
        def process(self, chords, beats, complexity, key, mode):
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
    assert score.analysis.confidence > 0
    assert any("Vocal separation failed" in warning for warning in score.analysis.warnings)
    assert any("without source separation" in warning for warning in score.analysis.warnings)
    assert not workspace.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("with_contour", [False, True])
@pytest.mark.parametrize("accompaniment", ["absent", "present", "missing_file"])
async def test_pipeline_reports_successful_vocal_separation(tmp_path, with_contour, accompaniment):
    from app.core.pipeline import AnalysisPipeline
    from app.models.analysis import BeatAnalysis, ChordAnalysis, MelodyAnalysis, MelodyMode, MelodyNote, RhythmSuggestion
    from app.models.audio import AudioAsset, NormalizedAudio
    from app.models.candidates import AnalyzerRun, TimingCandidate, TimingResult
    from app.postprocess.melody import MelodyPostProcessor
    from app.models.melody_contour import MelodyContour

    normalized = NormalizedAudio(path=tmp_path / "mix.wav", duration_seconds=8.0)
    vocals = NormalizedAudio(path=tmp_path / "vocals.wav", duration_seconds=8.0)
    vocals.path.write_bytes(b"vocal-stem")
    if accompaniment != "absent":
        vocals.accompaniment_path = tmp_path / "no_vocals.wav"
        if accompaniment == "present":
            vocals.accompaniment_path.write_bytes(b"accompaniment")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()

    class Source:
        async def fetch(self, request): return AudioAsset(path=normalized.path, source_type=SourceType.LOCAL)
    class Preprocessor:
        async def normalize(self, asset): return normalized
    class BeatAnalyzer:
        async def analyze_candidates(self, audio):
            return TimingResult(
                run=AnalyzerRun(engine="candidate-test", engine_version="1"),
                candidates=[TimingCandidate(bpm=120, beats=[0, 0.5], downbeats=[0])],
            )
        def project(self, result):
            return BeatAnalysis(bpm=result.candidates[0].bpm, engine=result.run.engine)
    class ChordAnalyzer:
        async def analyze(self, audio, beats): return ChordAnalysis()
    class ChordPost:
        def process(self, chords, beats, complexity, key, mode): return chords
    class Separator:
        async def separate(self, audio, mode): return vocals, True
    class MelodyAnalyzer:
        async def analyze(self, audio, beats, mode):
            assert audio is vocals
            return MelodyAnalysis(mode=MelodyMode.VOCAL, contour=MelodyContour(
                source_artifact_sha256="0" * 64, source_start=0, source_end=8,
                hop_seconds=0.5, frequencies_hz=(450.1,) * 16,
                voiced_probabilities=(0.1,) * 16,
            ) if with_contour else None, notes=[
                MelodyNote(id="n", start=0.0, end=0.25, midi=60, note="C4", confidence=0.9),
                MelodyNote(id="n2", start=0.25, end=0.5, midi=60, note="C4", confidence=0.9),
            ])
    class Mapper:
        def map_notes(self, melody): return melody
    class Rhythm:
        def suggest(self, beats, chords): return RhythmSuggestion()

    pipeline = AnalysisPipeline(
        Preprocessor(), BeatAnalyzer(), ChordAnalyzer(), MelodyAnalyzer(), ChordPost(),
        MelodyPostProcessor(), Rhythm(), Mapper(), Source(), Separator(), MelodyAnalyzer(),
    )
    score = await pipeline.run(
        SourceRequest(source_type=SourceType.LOCAL, path=normalized.path),
        {"melody_mode": "vocal", "separate_vocals": True, "_artifact_directory": str(artifacts)},
    )

    assert "Vocal isolation was applied before melody extraction." in score.analysis.warnings
    assert score.analysis.confidence > 0
    assert not any("without source separation" in warning for warning in score.analysis.warnings)
    assert (artifacts / "vocal-stem.wav").read_bytes() == b"vocal-stem"
    assert (artifacts / "accompaniment-stem.wav").is_file() is (accompaniment == "present")
    if accompaniment == "present":
        assert (artifacts / "accompaniment-stem.wav").read_bytes() == b"accompaniment"
    assert (artifacts / "raw-melody.wav").is_file()
    assert (artifacts / "final-melody.wav").is_file()
    assert (artifacts / "melody-contour.wav").is_file() is with_contour
    assert (artifacts / "melody-contour.json").is_file() is with_contour
    if with_contour:
        saved = MelodyContour.model_validate_json((artifacts / "melody-contour.json").read_text())
        assert saved.frequencies_hz == (450.1,) * 16
        assert saved.voiced_probabilities == (0.1,) * 16
    import json
    raw_candidates = json.loads((artifacts / "melody-candidates.json").read_text())
    assert raw_candidates["schema_version"] == "1.0"
    assert raw_candidates["source_separated"] is True
    assert raw_candidates["analysis"]["notes"][0]["id"] == "n"
    assert raw_candidates["analysis"]["notes"][0]["end"] == 0.25
    assert len(raw_candidates["analysis"]["notes"]) == 2
    assert len(score.melody) == 1
    assert score.melody[0].end == 0.5
    timing_artifact = artifacts / "timing-candidates.json"
    assert timing_artifact.is_file()
    assert '"raw_artifact": "timing-candidates.json"' in timing_artifact.read_text()
    assert score.provenance.beat_engine == "candidate-test"
