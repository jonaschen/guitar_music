import pytest
from app.evaluation.source_timed_audit import build_candidate, connected_note_frames, rounded_contour_frames, frame_faithful_notes, frame_loss
from app.models.score import SongScore, SongInfo
from app.models.melody_contour import MelodyContour
from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.postprocess.melody import MelodyPostProcessor


def test_candidate_preserves_original_and_backing_without_grid_snapping():
    score = SongScore(song=SongInfo(duration_seconds=1, source_start_seconds=18.5),
                      beats=[BeatInfo(time=.07, beat=1, measure=1), BeatInfo(time=.42, beat=2, measure=1)],
                      chords=[ChordEvent(id="c", start=0, end=1, symbol="C")],
                      melody=[MelodyNote(id="old", start=.07, end=.42, midi=64, note="E4")])
    before = score.model_dump_json()
    contour = MelodyContour(source_artifact_sha256="0"*64, source_start=0, source_end=1,
                            hop_seconds=.025, frequencies_hz=tuple(440*2**((n-69)/12) for n in [64]*20+[65]*20),
                            voiced_probabilities=(.9,)*40)
    result = build_candidate(score, contour)
    assert [n.midi for n in result.melody] == [64, 65]
    assert [(n.start,n.end) for n in result.melody] == [(0,.5),(.5,1)]
    assert result.beats == score.beats and result.chords == score.chords and result.rhythm == score.rhythm
    assert result.song.source_start_seconds == 18.5
    assert result.provenance.parameters["listening_candidate"] is True
    assert score.model_dump_json() == before
    assert all(n.string is not None and n.fret is not None for n in result.melody)
    with pytest.raises(ValueError, match="timeline"):
        build_candidate(score.model_copy(update={"song": SongInfo(duration_seconds=2)}), contour)


def test_source_timed_path_rejects_polyphonic_input_instead_of_silently_selecting():
    notes=[MelodyNote(id="a", start=0,end=.5,midi=60,note="C4"),
           MelodyNote(id="b",start=.2,end=.7,midi=64,note="E4")]
    with pytest.raises(ValueError,match="monophonic"):
        MelodyPostProcessor().process_source_timed(notes)


def test_connected_controls_preserve_rests_and_half_open_note_boundaries():
    contour = MelodyContour(source_artifact_sha256="0"*64, source_start=0, source_end=.5,
                            hop_seconds=.1, frequencies_hz=(441, None, 467, 467, None),
                            voiced_probabilities=(.9, None, .9, .9, None))
    before = contour.model_dump_json()
    notes = [MelodyNote(id="a", start=0, end=.1, midi=69, note="A4"),
             MelodyNote(id="b", start=.2, end=.3, midi=70, note="Bb4"),
             MelodyNote(id="c", start=.3, end=.4, midi=69, note="A4")]
    frames = connected_note_frames(notes, contour)
    assert frames[1] is None and frames[4] is None
    assert [frames[i] for i in [0,2,3]] == pytest.approx([440, 440*2**(1/12), 440])
    rounded = rounded_contour_frames(contour)
    assert rounded[1] is None and rounded[4] is None
    assert [rounded[i] for i in [0,2,3]] == pytest.approx([440, 440*2**(1/12), 440*2**(1/12)])
    assert contour.model_dump_json() == before
    assert connected_note_frames([], contour) == [None]*5
    with pytest.raises(ValueError, match="monophonic"):
        connected_note_frames(notes + [notes[0]], contour)


def test_frame_reference_keeps_short_low_confidence_notes_and_exact_rests():
    contour = MelodyContour(source_artifact_sha256="0"*64, source_start=0, source_end=.095,
                            hop_seconds=.02, frequencies_hz=(440, None, 467, 467, 440),
                            voiced_probabilities=(.1, None, .2, .2, .1))
    notes = frame_faithful_notes(contour)
    assert len(notes) == 3
    assert notes[-1].end == .095
    assert notes[0].confidence == .1
    loss = frame_loss(rounded_contour_frames(contour), connected_note_frames(notes, contour), .02, 0, .095)
    assert loss == dict(voiced=4, dropped=0, changed_pitch=0, invented_voicing=0)
    assert frame_loss([440, 440, None], [None, 467, 440], .1, 0, .3) == dict(
        voiced=2, dropped=1, changed_pitch=1, invented_voicing=1)
    with pytest.raises(ValueError, match="counts"):
        frame_loss([440], [], .1, 0, .1)
