import json
import pytest
from app.analyzers.beats.timing_diagnostics import describe_observations, BeatProjectionError
from app.analyzers.beats.beat_this_adapter import BeatThisBeatAnalyzer
from app.core.pipeline import create_pipeline
from app.core.config import Settings, ChordEngine
from app.models.audio import SourceRequest, SourceType


def test_runs_do_not_bridge_bad_bar_or_invent_edge_downbeat():
    beats=[i*.5 for i in range(39)]
    down=[beats[i] for i in [0,4,8,12,16,18,22,26,30,34]]
    report=describe_observations(beats,down)
    assert report['beats_per_downbeat_interval']==[4,4,4,4,2,4,4,4,4]
    assert report['structurally_consistent_spans']==[
        dict(start=0,end=8,beats_per_bar=4,bars=4),dict(start=9,end=17,beats_per_bar=4,bars=4)]
    assert not report['automatic_repair'] and report['musical_verdict']=='unconfirmed'
    assert report['beats']==beats and report['downbeats']==down


@pytest.mark.parametrize('beats,down',[([],[]),([0,.5],[0]),([0,.5,1],[0,.7]),([0,.5,float('nan')],[0,1]),([0,.5,.5],[0,.5])])
def test_invalid_observations_never_propose_spans(beats,down):
    report=describe_observations(beats,down)
    assert not report['aligned_observations']
    assert report['structurally_consistent_spans']==[]
    json.dumps(report,allow_nan=False)


@pytest.mark.asyncio
async def test_pipeline_saves_evidence_before_rejecting_and_skips_later_analysis(sample_wav,tmp_path):
    pipeline=create_pipeline(Settings(chord_engine=ChordEngine.CHROMAGRAM))
    beats=[i*.5 for i in range(14)];down=[0,2,3,5]
    pipeline.beat_analyzer=BeatThisBeatAnalyzer(predictor=lambda _: (beats,down))
    class Forbidden:
        supports_unmetered = False
        def __getattr__(self,name): pytest.fail('Chord/melody processing must not run after grid rejection')
    pipeline.chord_analyzer=Forbidden();pipeline.melody_analyzer=Forbidden()
    with pytest.raises(BeatProjectionError,match='Inconsistent'):
        await pipeline.run(SourceRequest(source_type=SourceType.LOCAL,path=sample_wav,rights_confirmed=True),
                           {'melody_mode':'off','_artifact_directory':str(tmp_path)})
    report=json.loads((tmp_path/'timing-rejection.json').read_text())
    assert report['beats']==beats and report['downbeats']==down
    assert report['parameters']['beat_this_dbn'] is False
    assert not (tmp_path/'chord-analysis.json').exists()


def test_pulse_density_drop_and_gap_are_reported_without_inserting_beats():
    from app.analyzers.beats.pulse_intervals import describe_pulse_intervals
    beats=[0,.65,1.30,1.95,3.25,4.55,8.45,9.10,9.75,10.40]
    before=list(beats)
    report=describe_pulse_intervals(beats)
    assert report['median_seconds']==pytest.approx(.65)
    assert [x['ratio_to_median'] for x in report['deviations']]==pytest.approx([2,2,6])
    assert beats==before
    assert all(x['kind']=='long_interval' for x in report['deviations'])


def test_uniform_half_speed_is_not_called_a_local_gap():
    from app.analyzers.beats.pulse_intervals import describe_pulse_intervals
    report=describe_pulse_intervals([0,1.3,2.6,3.9,5.2])
    assert report['deviations']==[]
    assert report['median_seconds']==pytest.approx(1.3)
