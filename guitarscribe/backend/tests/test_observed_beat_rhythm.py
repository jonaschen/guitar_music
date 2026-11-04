import pytest
from app.models.analysis import BeatInfo, ChordEvent, RhythmSuggestion
from app.models.score import SongScore, SongInfo
from app.services.downbeat_rhythm import BEAT_PATTERN_ID, beat_events
from app.exporters.midi import compile_playback_manifest, export_midi
from app.services.revisions import RevisionStore


def score():
    return SongScore(song=SongInfo(duration_seconds=8),
        beats=[BeatInfo(time=i*.5,beat=i%4+1,measure=i//4+1) for i in range(16)],
        chords=[ChordEvent(id='c',symbol='C',start=0,end=8)],
        rhythm=RhythmSuggestion(pattern_id=BEAT_PATTERN_ID,subdivision=4,display=['D']*4))


def test_held_harmony_has_observed_attacks_and_first_beat_accent(tmp_path):
    s=score();before=s.model_dump_json();events=beat_events(s)
    assert [e.start for e in events]==[b.time for b in s.beats]
    assert events[0].velocity>events[1].velocity and events[0].velocity==events[4].velocity
    assert [(e.end,e.sustain_end) for e in events]==[(i*.5+.5,i*.5+.5) for i in range(16)]
    assert [e for e in compile_playback_manifest(s).events if e.track=='guitar']==events
    store=RevisionStore(tmp_path);restored=store.load(store.save(s))
    assert export_midi(restored)==export_midi(s)
    assert s.model_dump_json()==before


def test_offbeat_harmony_waits_for_next_beat_without_extra_attack():
    s=score();s.chords=[ChordEvent(id='c',symbol='C',start=0,end=.75),
        ChordEvent(id='g',symbol='G',start=.75,end=8)]
    events=beat_events(s)
    assert [e.start for e in events]==[b.time for b in s.beats]
    assert [(e.start,e.source_id,e.end) for e in events[:3]]==[(0,'c',.5),(.5,'c',1),(1,'g',1.5)]


@pytest.mark.parametrize('explicit',[False,True])
def test_silence_is_not_filled_or_bridged(explicit):
    s=score();s.chords=[ChordEvent(id='c',symbol='C',start=0,end=.75)]
    if explicit:s.chords.append(ChordEvent(id='n',symbol='N.C.',start=.75,end=2.2))
    s.chords.append(ChordEvent(id='g',symbol='G',start=2.2,end=8))
    events=beat_events(s)
    assert [(e.start,e.end) for e in events[:3]]==[(0,.5),(.5,.75),(2.5,3)]


def test_variable_tempo_and_pickup_follow_observed_times_without_tail_attacks():
    s=score();s.beats=[BeatInfo(time=.2,beat=4,measure=0)]+[
        BeatInfo(time=t,beat=i+1,measure=1) for i,t in enumerate([.7,1.3,2.1,3.0])]
    assert [e.start for e in beat_events(s)]==[.2,.7,1.3,2.1,3.0]
    assert beat_events(s)[0].velocity<beat_events(s)[1].velocity


def test_unmetered_and_broken_grid_cannot_use_observed_pattern():
    s=score();s.beats[2].beat=1
    with pytest.raises(ValueError):compile_playback_manifest(s)
    s=score();s.analysis.timing_status='unmetered';s.analysis.bpm=0;s.analysis.time_signature='';s.beats=[]
    with pytest.raises(ValueError):compile_playback_manifest(s)
