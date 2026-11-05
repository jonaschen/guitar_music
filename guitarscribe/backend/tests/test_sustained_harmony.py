import pytest
from app.models.score import SongScore,SongInfo
from app.models.analysis import BeatInfo,ChordEvent,RhythmSuggestion
from app.evaluation.sustained_harmony import audit_sustained_harmony


def score():
    return SongScore(song=SongInfo(duration_seconds=4),
        beats=[BeatInfo(time=i*.5,beat=i%4+1,measure=i//4+1) for i in range(8)],
        chords=[ChordEvent(id='c',symbol='C',start=0,end=.25),ChordEvent(id='g',symbol='G',start=.25,end=4)],
        rhythm=RhythmSuggestion(pattern_id='observed-downbeats-v1'))


def test_short_first_chord_rings_across_other_score_harmony_without_editing():
    s=score();original=s.model_dump_json();r=audit_sustained_harmony(s,0,4)
    assert r['majority_other_events']==1
    assert r['rows'][0]['support_seconds']==.25
    assert r['rows'][0]['other_score_harmony_seconds']==1.75
    assert r['rows'][1]['support_fraction']==1
    assert s.model_dump_json()==original and not r['musical_accuracy_evaluated']


def test_only_actual_sustain_is_counted_and_clip_offset_is_explicit():
    s=score();s.chords[1].start=1
    r=audit_sustained_harmony(s,.1,3)
    assert r['rows'][0]['clip_end']==.25 # Gap damps the chord; no invented sustain.
    assert r['rows'][0]['other_score_harmony_seconds']==0
    assert r['rows'][1]['player_seconds']==pytest.approx(1.9)


def test_same_pitch_set_does_not_become_false_harmony_change():
    s=score();s.chords[1].symbol='C'
    r=audit_sustained_harmony(s,0,4)
    assert r['majority_other_events']==0 and r['other_score_harmony_seconds']==0


@pytest.mark.parametrize('scope',[(0,5),(-1,2),(2,2)])
def test_bad_scope_rejected(scope):
    with pytest.raises(ValueError):audit_sustained_harmony(score(),*scope)
