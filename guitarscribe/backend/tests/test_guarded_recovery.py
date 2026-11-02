import json
from pathlib import Path
import pytest

from app.analyzers.beats.guarded_recovery import check_recovery
from app.analyzers.beats.beat_this_adapter import BeatThisBeatAnalyzer
from app.analyzers.beats.timing_diagnostics import BeatProjectionError
from app.core.config import Settings, BeatEngine, ChordEngine
from app.core.pipeline import create_pipeline
from app.models.audio import NormalizedAudio, SourceRequest, SourceType


def observations():
    beats = [i*.25 for i in range(32)]
    # Six stable bars followed by one wrong downbeat in the last bar.
    primary_down = [0,1,2,3,4,5,6,6.5,7]
    return beats, primary_down, beats[:], list(range(8))


def test_local_error_can_recover_without_moving_continuous_beats_or_downbeats():
    b, d, cb, cd = observations(); before=json.dumps([b,d,cb,cd])
    result, report=check_recovery(b,d,cb,cd,8,'test')
    assert result is not None and report['eligible'] and result.time_signature=='4/4'
    assert [v.time for v in result.beats]==cb
    assert report['musical_verdict']=='unconfirmed' and json.dumps([b,d,cb,cd])==before


def test_three_four_recovery_is_not_forced_into_four_four():
    beats=[i*.25 for i in range(30)];down=[i*.75 for i in range(10)]
    primary=down[:];primary.insert(8,5.5)
    result,report=check_recovery(beats,primary,beats,down,8,'test')
    assert report['eligible'] and result.time_signature=='3/4'


@pytest.mark.parametrize('kind', ['shifted_phase','double_density','half_density','local_density','missing_reference','outside','invalid'])
def test_legal_looking_or_unsupported_grids_are_not_silently_accepted(kind):
    b,d,cb,cd=observations();duration=8
    if kind=='shifted_phase':cd=[v+.25 for v in cd]  # Same speed, wrong first beat.
    elif kind=='double_density':cb=[i*.125 for i in range(64)];cd=[i*.5 for i in range(16)]
    elif kind=='half_density':cb=cb[::2];cd=cd[::2]
    elif kind=='local_density':cb=cb[:16]+[4+i*.5 for i in range(16)];cd=cb[::4];duration=12
    elif kind=='missing_reference':d=[0,.5,1,1.5]
    elif kind=='outside':duration=7
    else:cb=[0,float('nan'),1]
    result,report=check_recovery(b,d,cb,cd,duration,'test')
    assert result is None and not report['eligible'] and report['reasons']
    json.dumps(report,allow_nan=False)


def injected(primary=None, recovery=None):
    b,d,cb,cd=observations();calls=[];token=object()
    def frames(_):calls.append('frames');return (token,)
    def first(x):assert x is token;calls.append('minimal');return primary or (b,d)
    def second(x):assert x is token;calls.append('dbn');return recovery or (cb,cd)
    engine=BeatThisBeatAnalyzer(recovery_enabled=True,frame_predictor=frames,primary_decoder=first,recovery_decoder=second)
    return engine,calls


@pytest.mark.asyncio
async def test_both_decoders_share_exactly_one_inference_and_retained_primary_is_never_replaced():
    engine,calls=injected();audio=NormalizedAudio(path=Path('unused.wav'),duration_seconds=8)
    result=await engine.analyze(audio)
    assert calls==['frames','minimal','dbn'] and engine.parameters['beat_this_dbn']
    assert engine.recovery_report['eligible'] and len(result.beats)==32
    # Reusing an analyzer does not leak a prior recovery into the next result.
    engine._primary_decoder=lambda _: observations()[2:]
    await engine.analyze(audio)
    assert calls.count('dbn')==1 and not engine.parameters['beat_this_dbn']
    assert engine.recovery_report is None and engine.parameters['beat_recovery_status']=='primary_retained'


@pytest.mark.asyncio
async def test_failed_recovery_serializes_original_evidence_without_cycles():
    b,d,cb,cd=observations()
    engine,_=injected(recovery=(cb,[v+.25 for v in cd]))
    with pytest.raises(BeatProjectionError) as caught:
        await engine.analyze(NormalizedAudio(path=Path('unused'),duration_seconds=8))
    evidence=caught.value.evidence
    json.dumps(evidence,allow_nan=False)
    assert evidence['beats']==b and evidence['downbeats']==d
    assert not evidence['recovery']['eligible'] and not engine.parameters['beat_this_dbn']


@pytest.mark.asyncio
async def test_missing_optional_decoder_preserves_normal_unmetered_fallback():
    engine,_=injected()
    def fail(*_):raise ImportError('optional decoder missing')
    engine._recovery_decoder=fail
    with pytest.raises(BeatProjectionError) as caught:
        await engine.analyze(NormalizedAudio(path=Path('unused'),duration_seconds=8))
    assert caught.value.evidence['recovery']['reasons']==['decoder_unavailable_or_failed']
    json.dumps(caught.value.evidence,allow_nan=False)


@pytest.mark.asyncio
async def test_disabled_recovery_never_invokes_optional_decoder():
    engine,calls=injected();engine.recovery_enabled=False
    with pytest.raises(BeatProjectionError) as caught:
        await engine.analyze(NormalizedAudio(path=Path('unused'),duration_seconds=8))
    assert calls==['frames','minimal'] and 'recovery' not in caught.value.evidence


@pytest.mark.asyncio
async def test_pipeline_rejected_candidate_keeps_chords_and_both_diagnostics(sample_wav,tmp_path):
    from app.models.analysis import ChordAnalysis,ChordEvent
    class Chords:
        supports_unmetered=True
        async def analyze(self,audio,beats):
            assert beats is None
            return ChordAnalysis(chords=[ChordEvent(id='a',symbol='C',start=0,end=audio.duration_seconds)],engine='test')
    pipeline=create_pipeline(Settings(chord_engine=ChordEngine.CHROMAGRAM))
    b,d,cb,cd=observations();pipeline.beat_analyzer,_=injected(recovery=(cb,[v+.25 for v in cd]))
    pipeline.chord_analyzer=Chords()
    score=await pipeline.run(SourceRequest(source_type=SourceType.LOCAL,path=sample_wav,rights_confirmed=True),
                             {'melody_mode':'off','_artifact_directory':str(tmp_path)})
    assert score.analysis.timing_status=='unmetered' and not score.beats and len(score.chords)==1
    assert not json.loads((tmp_path/'timing-recovery.json').read_text())['eligible']
    assert json.loads((tmp_path/'timing-rejection.json').read_text())['beats']==b


def test_recovery_configuration_defaults_off(monkeypatch):
    monkeypatch.delenv('GUITARSCRIBE_BEAT_RECOVERY_ENABLED',raising=False)
    assert not Settings.from_env().beat_recovery_enabled
    monkeypatch.setenv('GUITARSCRIBE_BEAT_RECOVERY_ENABLED','true')
    settings=Settings.from_env();settings.beat_engine=BeatEngine.BEAT_THIS_SMALL;settings.chord_engine=ChordEngine.CHROMAGRAM
    assert create_pipeline(settings).beat_analyzer.recovery_enabled


@pytest.mark.asyncio
async def test_pipeline_saves_recovery_evidence_and_provenance(sample_wav,tmp_path):
    settings=Settings(beat_engine=BeatEngine.BEAT_THIS_SMALL,chord_engine=ChordEngine.CHROMAGRAM)
    pipeline=create_pipeline(settings);pipeline.beat_analyzer,_=injected()
    score=await pipeline.run(SourceRequest(source_type=SourceType.LOCAL,path=sample_wav,rights_confirmed=True),
                             {'melody_mode':'off','_artifact_directory':str(tmp_path)})
    evidence=json.loads((tmp_path/'timing-recovery.json').read_text())
    assert evidence['eligible'] and evidence['primary']['beats_per_downbeat_interval'][-2:]==[2,2]
    assert score.analysis.timing_status=='metered' and score.provenance.parameters['beat_this_dbn']
    assert score.provenance.parameters['beat_recovery_status']=='recovered'
    assert not (tmp_path/'timing-rejection.json').exists()
