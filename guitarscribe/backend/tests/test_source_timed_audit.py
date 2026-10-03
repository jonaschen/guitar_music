import pytest
from app.evaluation.source_timed_audit import build_candidate
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
