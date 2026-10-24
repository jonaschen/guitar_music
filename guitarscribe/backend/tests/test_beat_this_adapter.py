from pathlib import Path
import pytest
from app.analyzers.beats.beat_this_adapter import BeatThisBeatAnalyzer
from app.analyzers.beats.librosa_beats import LibrosaBeatAnalyzer
from app.core.config import BeatEngine, Settings, ChordEngine
from app.core.pipeline import create_pipeline
from app.models.audio import NormalizedAudio


def test_factory_is_opt_in_and_does_not_load_model(monkeypatch):
    monkeypatch.delenv('GUITARSCRIBE_BEAT_ENGINE',raising=False)
    settings=Settings.from_env();settings.chord_engine=ChordEngine.CHROMAGRAM
    assert isinstance(create_pipeline(settings).beat_analyzer,LibrosaBeatAnalyzer)
    monkeypatch.setenv('GUITARSCRIBE_BEAT_ENGINE','beat_this_small')
    settings=Settings.from_env();settings.chord_engine=ChordEngine.CHROMAGRAM
    engine=create_pipeline(settings).beat_analyzer
    assert isinstance(engine,BeatThisBeatAnalyzer) and engine._predictor is None


@pytest.mark.asyncio
async def test_detected_pickup_is_preserved_and_invalid_meter_is_not_silently_faked():
    audio=NormalizedAudio(path=Path('unread.wav'),duration_seconds=5)
    engine=BeatThisBeatAnalyzer(predictor=lambda _:([i*.5 for i in range(10)],[1,3]))
    result=await engine.analyze(audio)
    assert result.beats[0].beat==3 and result.beats[0].measure==0
    engine=BeatThisBeatAnalyzer(predictor=lambda _:([i*.5 for i in range(10)],[0,3]))
    with pytest.raises(ValueError,match='Inconsistent'):
        await engine.analyze(audio)


@pytest.mark.asyncio
async def test_pipeline_retains_learned_pickup_and_provenance(sample_wav,tmp_path):
    from app.models.audio import SourceRequest, SourceType
    settings=Settings(beat_engine=BeatEngine.BEAT_THIS_SMALL,chord_engine=ChordEngine.CHROMAGRAM)
    pipeline=create_pipeline(settings)
    pipeline.beat_analyzer=BeatThisBeatAnalyzer(predictor=lambda _:([i*.5 for i in range(14)],[1,3,5]))
    artifacts=tmp_path/'artifacts';artifacts.mkdir()
    score=await pipeline.run(SourceRequest(source_type=SourceType.LOCAL,path=sample_wav,rights_confirmed=True),
                             {'_artifact_directory':str(artifacts)})
    assert score.beats[0].measure==0 and score.beats[0].beat==3
    assert [b.time for b in score.beats if b.beat==1]==[1,3,5]
    assert score.provenance.beat_engine=='beat-this'
    assert score.provenance.tempo_map_version=='learned-downbeats-v1'
    assert score.provenance.parameters['beat_this_checkpoint']=='small0'
    assert (artifacts/'timing-analysis.json').is_file()
