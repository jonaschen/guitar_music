import pytest
from xml.etree import ElementTree

from app.evaluation.bounded_checkpoint import build_score
from app.models.score import SongScore, SongInfo
from app.models.melody_contour import MelodyContour
from app.models.analysis import MelodyNote, ChordEvent
from app.services.revisions import RevisionStore
from app.exporters.midi import compile_playback_manifest, export_midi
from app.exporters.musicxml import export_musicxml


def source():
    score = SongScore(song=SongInfo(duration_seconds=.5,source_start_seconds=18.5),
        chords=[ChordEvent(id="c",start=0,end=.5,symbol="C")])
    contour = MelodyContour(source_artifact_sha256="0"*64, source_start=0,source_end=.5,
        hop_seconds=.02, frequencies_hz=tuple([440]*10+[None]*5+[493.883301256]*10),
        voiced_probabilities=tuple([.2]*25))
    return score,contour


def test_candidate_is_editable_copy_with_exact_time_and_export_support(tmp_path):
    original,contour = source()
    before = original.model_dump_json()
    candidate = build_score(original,contour)
    assert original.model_dump_json() == before
    assert candidate.chords == original.chords and candidate.beats == original.beats
    assert candidate.song.source_start_seconds == 18.5
    assert [(n.start,n.end) for n in candidate.melody] == [(0,.2),(.3,.5)]
    assert all(n.string is not None for n in candidate.melody)
    events = [e for e in compile_playback_manifest(candidate).events if e.track == "melody"]
    assert [(e.start,e.end,e.pitches) for e in events] == [(n.start,n.end,(n.midi,)) for n in candidate.melody]
    assert export_midi(candidate).startswith(b"MThd")
    assert ElementTree.fromstring(export_musicxml(candidate)).find(".//note/pitch") is not None
    # Temporary store only: demonstrate the existing revision model accepts it.
    store = RevisionStore(tmp_path)
    revision = store.save(candidate)
    loaded = store.load(revision)
    assert loaded == candidate
    loaded.melody[0].edited = True
    assert not candidate.melody[0].edited


def test_rejects_edited_transposed_or_mismatched_inputs():
    score,contour = source()
    score.melody = [MelodyNote(id="manual",start=0,end=.2,midi=69,note="A4",edited=True)]
    with pytest.raises(ValueError,match="unedited"):
        build_score(score,contour)
    score.melody = []
    score.key_context.transpose_semitones = 2
    with pytest.raises(ValueError,match="untransposed"):
        build_score(score,contour)
    score.key_context.transpose_semitones = 0
    score.song.duration_seconds = 1
    with pytest.raises(ValueError,match="timelines"):
        build_score(score,contour)
