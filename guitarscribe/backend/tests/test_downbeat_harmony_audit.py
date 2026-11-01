import pytest
from app.models.analysis import BeatInfo,ChordEvent,RhythmSuggestion
from app.models.score import SongScore,SongInfo
from app.services.downbeat_rhythm import PATTERN_ID
from app.services.downbeat_harmony_audit import audit_downbeat_harmony
from app.services.chord_grid_candidate import build_chord_grid_candidate
from app.exporters.midi import compile_playback_manifest,export_midi
from app.services.revisions import RevisionStore


def source():
    return SongScore(song=SongInfo(duration_seconds=8),
        beats=[BeatInfo(time=i*.5,beat=i%4+1,measure=i//4+1) for i in range(17)],
        chords=[ChordEvent(id='a',symbol='C',start=0,end=2.004),ChordEvent(id='b',symbol='G',start=2.004,end=8)],
        rhythm=RhythmSuggestion(pattern_id=PATTERN_ID,subdivision=4,display=['D',None,None,None]))


def test_four_millisecond_boundary_can_delay_a_whole_bar_without_changing_stroke_grid(tmp_path):
    s=source();before=s.model_dump_json();audit=audit_downbeat_harmony(s,0,8)
    boundary=audit['rows'][1]['nearby_late_boundary']
    assert boundary['lag_seconds']==pytest.approx(.004)
    assert boundary['first_scheduled_attack']==4
    assert boundary['wait_seconds']==pytest.approx(1.996)
    assert s.model_dump_json()==before
    c,_=build_chord_grid_candidate(s,scope=(0,8));fixed=audit_downbeat_harmony(c,0,8)
    assert [r['symbol'] for r in audit['rows']]==['C','C','G','G']
    assert [r['symbol'] for r in fixed['rows']]==['C','G','G','G']
    assert [r['time'] for r in fixed['rows']]==[r['time'] for r in audit['rows']]
    assert fixed['rows'][1]['nearby_late_boundary'] is None
    store=RevisionStore(tmp_path);parent=store.save(s);revision=store.fork(parent,c)
    assert store.load(parent)==s
    assert compile_playback_manifest(store.load(revision))==compile_playback_manifest(c)
    assert export_midi(store.load(revision))==export_midi(c)


def test_short_unstruck_chord_is_reported_not_deleted_or_audited_as_incorrect():
    s=source();s.chords=[ChordEvent(id='a',symbol='C',start=0,end=2.004),
        ChordEvent(id='b',symbol='G',start=2.004,end=2.05),ChordEvent(id='c',symbol='F',start=2.05,end=8)]
    audit=audit_downbeat_harmony(s,0,8)
    assert audit['rows'][1]['nearby_late_boundary']['first_scheduled_attack'] is None
    assert [r['chord_id'] for r in audit['unstruck_segments']]==['b']
    c,_=build_chord_grid_candidate(s,scope=(0,8))
    assert c.chords==s.chords


def test_gap_and_manual_chords_are_not_silently_retimed():
    s=source();s.chords[0].end=2
    assert audit_downbeat_harmony(s,0,8)['rows'][1]['symbol'] is None
    c,_=build_chord_grid_candidate(s,scope=(0,8));assert c.chords==s.chords
    s=source();s.chords[1].edited=True
    assert audit_downbeat_harmony(s,0,8)['rows'][1]['nearby_late_boundary']['contains_manual_edit']
    c,_=build_chord_grid_candidate(s,scope=(0,8));assert c.chords==s.chords


@pytest.mark.parametrize('case',['mode','range','grid'])
def test_invalid_audit_inputs(case):
    s=source();end=8
    if case=='mode':s.rhythm.pattern_id='other'
    elif case=='range':end=9
    else:s.beats[1].beat=1
    with pytest.raises(ValueError):audit_downbeat_harmony(s,0,end)
