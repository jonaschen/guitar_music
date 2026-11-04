from pathlib import Path
import pytest
from app.analyzers.beats.beat_this_main import BeatThisMainAnalyzer
from app.analyzers.beats.beat_this_adapter import BeatThisBeatAnalyzer
from app.analyzers.beats.timing_diagnostics import BeatProjectionError
from app.core.config import Settings,BeatEngine,ChordEngine
from app.core.pipeline import create_pipeline
from app.models.audio import NormalizedAudio


def test_main_engine_is_explicit_and_lazy_with_existing_small_engine_unchanged(monkeypatch):
    monkeypatch.setenv('GUITARSCRIBE_BEAT_ENGINE','beat_this_main_dbn')
    settings=Settings.from_env();settings.chord_engine=ChordEngine.CHROMAGRAM
    main=create_pipeline(settings).beat_analyzer
    assert isinstance(main,BeatThisMainAnalyzer) and main._predictor is None
    settings.beat_engine=BeatEngine.BEAT_THIS_SMALL
    assert isinstance(create_pipeline(settings).beat_analyzer,BeatThisBeatAnalyzer)
    assert Settings().beat_engine==BeatEngine.LIBROSA


@pytest.mark.asyncio
async def test_main_projection_retains_observed_times_and_provenance():
    beats=[i*.5 for i in range(20)];downs=[0,2,4,6,8]
    engine=BeatThisMainAnalyzer(predictor=lambda path:(beats,downs))
    result=await engine.analyze(NormalizedAudio(path=Path('unused'),duration_seconds=10))
    assert [b.time for b in result.beats]==beats
    assert engine.parameters['beat_this_checkpoint']=='final0'
    assert engine.parameters['beat_this_dbn'] is True
    assert engine.parameters['beat_quality_status']=='passed'


@pytest.mark.asyncio
async def test_structurally_legal_double_density_is_rejected_with_evidence():
    beats=[i*.5 for i in range(81)]+[40+i*.25 for i in range(1,81)]
    downs=[i*2 for i in range(21)]+[40+i for i in range(1,21)]
    engine=BeatThisMainAnalyzer(predictor=lambda path:(beats,downs))
    with pytest.raises(BeatProjectionError) as error:
        await engine.analyze(NormalizedAudio(path=Path('unused'),duration_seconds=61))
    assert 'window_density_switch' in error.value.evidence['issues']
    assert error.value.evidence['beats']==beats
    assert engine.parameters['beat_quality_status']=='rejected'


@pytest.mark.asyncio
async def test_existing_valid_primary_is_retained_without_loading_main():
    from app.models.analysis import BeatAnalysis
    expected=BeatAnalysis(bpm=123)
    class Primary:
        parameters={'beat_this_checkpoint':'small0'}
        recovery_report={'eligible':True}
        async def analyze(self,audio):return expected
    engine=BeatThisMainAnalyzer(primary=Primary(),predictor=lambda _:pytest.fail('Do not rerun working timing'))
    assert await engine.analyze(None) is expected
    assert engine.parameters==Primary.parameters
    assert engine.recovery_report==Primary.recovery_report


@pytest.mark.asyncio
async def test_continuity_uses_same_frames_and_records_original_failure():
    frames=('beat frames','downbeat frames')
    base=[i*.5 for i in range(161)]+[80+i*.25 for i in range(1,41)]
    base_down=[i*2 for i in range(41)]+[80+i for i in range(1,11)]
    repaired=[i*.5 for i in range(180)];downs=[i*2 for i in range(45)]
    calls=[]
    def continuity(b,d,reference):
        assert (b,d)==frames and reference['eligible']
        calls.append(reference)
        return repaired,downs
    engine=BeatThisMainAnalyzer(frame_predictor=lambda _:frames,decoder=lambda *_:(base,base_down),continuity_decoder=continuity)
    result=await engine.analyze(NormalizedAudio(path=Path('unused'),duration_seconds=91))
    assert [b.time for b in result.beats]==repaired
    assert len(calls)==1
    assert engine.recovery_report['primary']['engineering_pass'] is False
    assert engine.recovery_report['candidate']['engineering_pass'] is True
    assert engine.parameters['main_recovery_decoder']=='continuity'


@pytest.mark.asyncio
async def test_unavailable_optional_recovery_keeps_unmetered_fallback_contract():
    class Primary:
        parameters={'beat_this_checkpoint':'small0'}
        async def analyze(self,audio):raise BeatProjectionError('original',{'beats':[0,1]})
    def unavailable(_):raise RuntimeError('missing optional dependency')
    engine=BeatThisMainAnalyzer(primary=Primary(),predictor=unavailable)
    with pytest.raises(BeatProjectionError) as error:
        await engine.analyze(NormalizedAudio(path=Path('unused'),duration_seconds=10))
    assert error.value.evidence['beats']==[0,1]
    assert engine.parameters['main_recovery_status']=='rejected'
