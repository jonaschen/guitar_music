from app.evaluation.melody_trace import trace_melody_postprocess
from app.models.analysis import MelodyMode, MelodyNote
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
