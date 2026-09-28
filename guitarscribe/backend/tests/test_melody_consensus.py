from app.models.analysis import MelodyNote
from app.evaluation.melody_consensus import pitch_support, rerank_with_reference


def note(identity, midi, start=1, end=2, confidence=0.9):
    return MelodyNote(id=identity, midi=midi, note="test", start=start, end=end, confidence=confidence)


def test_supported_existing_candidate_replaces_wrong_semitone_without_mutation():
    raw = [note("flat", 63), note("natural", 64)]
    before = [n.model_dump() for n in raw]
    selected, decisions = rerank_with_reference(raw, raw, [raw[0]], [note("ref", 64)])
    assert selected[0].midi == 64
    assert decisions[0]["new_support"] == 1
    selected[0].end = 3
    assert [n.model_dump() for n in raw] == before


def test_no_invention_no_octave_equivalence_and_no_weak_support_override():
    raw = [note("flat", 63), note("natural", 64)]
    for reference in [[], [note("ref", 76)], [note("ref", 64, confidence=0.2)], [note("ref", 64, start=1.8)]]:
        selected, decisions = rerank_with_reference(raw, raw, [raw[0]], reference)
        assert selected[0].id == "flat"
        assert not decisions
    selected, decisions = rerank_with_reference(raw[:1], raw[:1], raw[:1], [note("ref", 64)])
    assert selected[0].midi == 63
    assert not decisions


def test_support_is_union_and_uses_raw_timing_not_quantized_collision():
    raw = [note("flat", 63, 0, 0.2), note("natural", 64, 0.3, 0.5)]
    reference = [note("r1", 64, 0, 0.2), note("r2", 64, 0, 0.2)]
    assert pitch_support(note("n", 64, 0, 0.2), reference) == 1
    quantized = [n.model_copy(update={"start": 0, "end": 0.5}) for n in raw]
    selected, decisions = rerank_with_reference(raw, quantized, quantized[:1], reference)
    assert selected[0].id == "flat"
    assert not decisions
