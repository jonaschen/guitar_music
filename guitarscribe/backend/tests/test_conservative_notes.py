import pytest

from app.models.melody_contour import MelodyContour
from app.evaluation.conservative_notes import decode_conservatively, decode_bounded, audition
from app.evaluation.source_timed_audit import connected_note_frames, rounded_contour_frames, frame_loss


def contour(values):
    return MelodyContour(source_artifact_sha256="0" * 64, source_start=0,
                         source_end=len(values) * .02, hop_seconds=.02,
                         frequencies_hz=tuple(None if p is None else 440*2**((p-69)/12) for p in values),
                         voiced_probabilities=tuple(.1 for _ in values))


@pytest.mark.parametrize("middle", [[61], [61]*2, [60.55]*3, [64]])
def test_keeps_short_real_plateaus_long_changes_and_leaps(middle):
    source = contour([60]*5 + middle + [60]*5)
    notes, changes = decode_conservatively(source)
    assert not changes
    assert frame_loss(rounded_contour_frames(source), connected_note_frames(notes, source), .02, 0, source.source_end)["changed_pitch"] == 0


def test_only_bounded_boundary_chatter_is_merged_without_deletion():
    source = contour([60]*5 + [60.55]*2 + [60]*5)
    original = source.model_dump_json()
    notes, changes = decode_conservatively(source)
    assert len(notes) == 1 and len(changes) == 1
    assert notes[0].end == source.source_end
    assert notes[0].confidence == pytest.approx(.1)
    assert source.model_dump_json() == original
    assert frame_loss(rounded_contour_frames(source), connected_note_frames(notes, source), .02, 0, source.source_end) == dict(voiced=12, dropped=0, changed_pitch=2, invented_voicing=0)


@pytest.mark.parametrize("values", [[60]*5 + [None, 60.55] + [60]*5,
                                   [60.55] + [60]*5, [60]*5 + [60.55], [None]*5])
def test_preserves_rests_phrase_edges_and_empty_voicing(values):
    source = contour(values)
    notes, changes = decode_conservatively(source)
    assert not changes
    assert connected_note_frames(notes, source) == pytest.approx(rounded_contour_frames(source))


def test_bounded_path_preserves_short_notes_rests_confidence_and_true_semitones():
    source = contour([60]*5 + [61] + [60]*5 + [None] + [64])
    notes = decode_bounded(source)
    assert [n.midi for n in notes] == [60,61,60,64]
    assert all(n.confidence == pytest.approx(.1) for n in notes)
    assert frame_loss(rounded_contour_frames(source), connected_note_frames(notes, source), .02, 0, source.source_end) == dict(voiced=12, dropped=0, changed_pitch=0, invented_voicing=0)


def test_bounded_path_suppresses_rounding_chatter_but_respects_hard_error_bound():
    import math
    source = contour([60]*5 + [60.49,60.51]*5 + [60]*5 + [61]*5)
    notes = decode_bounded(source)
    assert [n.midi for n in notes] == [60,61]
    frames = connected_note_frames(notes, source)
    assert all(abs(12*math.log2(a/b)) <= .6+1e-9 for a,b in zip(frames, source.frequencies_hz))


def test_audition_creates_isolated_artifacts_and_refuses_overwrite(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(contour([60]*5+[61]*5).model_dump_json())
    output = tmp_path / "audition"
    report = audition(source, output, 0, .2)
    assert report["bounded_notes"] == 2
    assert (output / "G-bounded-connected.wav").exists()
    with pytest.raises(FileExistsError):
        audition(source, output, 0, .2)
