from app.evaluation.melody_trace import trace_melody_postprocess
from app.models.analysis import BeatInfo, MelodyMode, MelodyNote
from app.postprocess.melody import MelodyPostProcessor


def test_trace_matches_legacy_output_and_preserves_each_stage():
    notes = [MelodyNote(id="a", start=0, end=0.5, midi=60, note="C4", confidence=0.8),
             MelodyNote(id="b", start=0.5, end=1, midi=60, note="C4", confidence=0.8),
             MelodyNote(id="c", start=0.75, end=1.25, midi=64, note="E4", confidence=0.8)]
    before = [n.model_dump() for n in notes]
    trace = trace_melody_postprocess(notes, [], MelodyMode.VOCAL, 0, 2)
    assert [n.model_dump() for n in notes] == before
    assert trace["stages"]["raw_candidates"]["notes"][0]["end"] == 0.5
    assert trace["stages"]["onset_bucket_selection"]["structure"]["note_count"] == 3
    assert trace["stages"]["same_pitch_merge"]["notes"][0]["end"] == 1
    expected = MelodyPostProcessor().process([n.model_copy(deep=True) for n in notes], [], MelodyMode.VOCAL)
    assert trace["stages"]["same_pitch_merge"]["notes"] == [n.model_dump(mode="json") for n in expected]
    assert trace["stages"]["raw_candidates"]["timing_changes_from_raw"] == []
    assert trace["stages"]["same_pitch_merge"]["timing_changes_from_raw"][0]["duration_ratio"] == 2


def test_trace_exposes_short_note_lengthening_from_quantization():
    notes = [MelodyNote(id="passing", start=0.26, end=0.39, midi=61, note="C#4", confidence=0.8)]
    beats = [BeatInfo(time=time, beat=index + 1, measure=1) for index, time in enumerate([0, 0.5, 1])]
    trace = trace_melody_postprocess(notes, beats, MelodyMode.VOCAL, 0, 1)
    change = trace["stages"]["beat_quantization"]["timing_changes_from_raw"][0]
    assert change["id"] == "passing"
    assert 1.9 < change["duration_ratio"] < 2
    assert abs(change["start_shift_seconds"] + 0.01) < 1e-9
    assert abs(change["end_shift_seconds"] - 0.11) < 1e-9
    assert notes[0].end == 0.39
