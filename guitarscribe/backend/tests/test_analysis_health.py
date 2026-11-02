import json
import pytest
from app.models.score import SongScore,SongInfo,AnalysisSummary
from app.models.analysis import BeatInfo,ChordEvent,RhythmSuggestion
from app.services.analysis_health import build_analysis_health,pulse_density_summary,write_analysis_health
from app.services.downbeat_rhythm import PATTERN_ID


def source():
    return SongScore(song=SongInfo(duration_seconds=40),
        beats=[BeatInfo(time=i*.5,beat=i%4+1,measure=i//4+1) for i in range(80)],
        chords=[ChordEvent(id='a',start=0,end=20,symbol='C'),ChordEvent(id='b',start=20,end=40,symbol='G')],
        rhythm=RhythmSuggestion(pattern_id=PATTERN_ID,subdivision=4,display=['D',None,None,None]))


def test_stable_and_doubled_density_are_observations_not_musical_verdicts():
    stable=pulse_density_summary([i*.5 for i in range(80)],40)
    assert stable['valid'] and not stable['octave_density_changes']
    doubled=pulse_density_summary([i*.5 for i in range(40)]+list(range(20,40)),40)
    assert doubled['octave_density_changes']==[dict(before=[10,20],after=[20,30],interval_ratio=2)]
    # An actual doubling of tempo receives the same description, never auto-repair.
    faster=pulse_density_summary(list(range(20))+[20+i*.5 for i in range(40)],40)
    assert faster['octave_density_changes'][0]['interval_ratio']==.5


def test_an_isolated_gap_does_not_mean_a_whole_density_change():
    assert not pulse_density_summary([i*.5 for i in range(80) if i!=24],40)['octave_density_changes']


@pytest.mark.parametrize('beats',[[],[1],[0,0,1],[0,float('nan'),1],[True,1,2]])
def test_invalid_observations_are_reported_without_inventing_grid(beats):
    assert not pulse_density_summary(beats,40)['valid']


def test_score_and_playback_unchanged_and_report_is_written(tmp_path):
    s=source();before=s.model_dump_json();report=write_analysis_health(s,tmp_path)
    assert s.model_dump_json()==before
    assert report['playback']['guitar_events']==20
    assert not report['musical_accuracy_evaluated'] and not report['automatic_edits']
    assert report['human_feedback']=='not_loaded_or_overwritten'
    assert report['chords']['incomplete_voicing_ids']==[]  # Default C/G shapes resolve without editing the score.
    assert json.loads((tmp_path/'analysis-health.json').read_text())==report


def test_rejected_observations_stay_out_of_score_and_short_chords_are_not_filtered():
    s=source();s.analysis=AnalysisSummary(timing_status='unmetered',bpm=0,time_signature='');s.beats=[];s.rhythm=RhythmSuggestion()
    s.chords=[ChordEvent(id='a',symbol='C',start=0,end=.2),ChordEvent(id='b',symbol='G',start=.2,end=40)]
    r=build_analysis_health(s,dict(beats=[i*.5 for i in range(40)]+list(range(20,40)),rejection_reason='test'))
    assert r['timing_source']=='rejected_observations' and r['pulse_density']['octave_density_changes']
    assert r['chords']['under_half_second']==1 and r['playback']['guitar_events']==2
    assert not s.beats and len(s.chords)==2
