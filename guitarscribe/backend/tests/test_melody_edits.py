from xml.etree import ElementTree

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.analysis import MelodyNote
from app.models.score import SongScore, SongInfo
from app.services.melody_edits import MelodyEditRequest, edit_melody
from app.services.transposition import TranspositionService
from app.services.revisions import RevisionStore
from app.exporters.midi import compile_playback_manifest, export_midi
from app.exporters.musicxml import export_musicxml


def score():
    return SongScore(song=SongInfo(duration_seconds=4), melody=[
        MelodyNote(id="one", start=0, end=0.5, midi=60, note="C4", confidence=0.4, string=2, fret=1),
        MelodyNote(id="two", start=1, end=1.5, midi=62, note="D4", confidence=0.7),
    ])


def apply(original, operation, **fields):
    return edit_melody(MelodyEditRequest(score=original, operation=operation, **fields))


def test_edit_is_non_destructive_and_records_unclassified_evidence():
    original = score()
    before = original.model_dump_json()
    result = apply(original, "update", note_id="one", midi=64, start=0.1, end=0.75, source_job_id="job").score
    assert original.model_dump_json() == before
    note = result.melody[0]
    assert (note.midi, note.note, note.start, note.end, note.origin, note.edited) == (64, "E4", 0.1, 0.75, "user", True)
    assert note.confidence == 0.4
    assert result.guitar.tuning[6-note.string] + result.analysis.capo + note.fret == 64
    assert result.melody[1] == original.melody[1]
    record = result.melody_edits[-1]
    assert record.intent == "unclassified"
    assert record.source_job_id == "job"
    assert record.before == [original.melody[0]]
    assert record.after == [note]
    assert SongScore.model_validate_json(result.model_dump_json()) == result


def test_edit_in_transposed_key_survives_return_to_source_key():
    shifted = TranspositionService().transpose_score(score(), 2)
    result = apply(shifted, "update", note_id="one", midi=65, start=0, end=0.5).score
    assert result.melody[0].source_midi == 63
    back = TranspositionService().transpose_score(result, 0)
    assert back.melody[0].midi == 63
    assert TranspositionService().transpose_score(back, 2).melody[0].midi == 65


def test_explicit_tab_position_preserved_and_logged_with_capo_and_tuning():
    original = score()
    original.guitar.tuning = [38, 45, 50, 55, 59, 64]
    original.analysis.capo = 2
    result = apply(original, "update", note_id="one", midi=64, start=0, end=.5,
                   string=3, fret=7).score
    assert (result.melody[0].string, result.melody[0].fret) == (3, 7)
    assert result.melody_edits[-1].after[0] == result.melody[0]
    assert original.melody[0].midi == 60
    xml = export_musicxml(result)
    assert "<string>3</string>" in xml and "<fret>7</fret>" in xml
    timed = apply(result, "update", note_id="one", midi=64, start=0, end=.75).score
    assert (timed.melody[0].string, timed.melody[0].fret) == (3, 7)
    split = apply(timed, "split", note_id="one", split_time=.25).score
    assert all((n.string, n.fret) == (3, 7) for n in split.melody if n.start < .75)


@pytest.mark.parametrize("fields", [{"string": 2}, {"fret": 1}, {"string": 2, "fret": 2},
                                      {"string": 6, "fret": 20}, {"string": 7, "fret": 0}])
def test_invalid_explicit_tab_is_rejected(fields):
    with pytest.raises(ValueError):
        apply(score(), "update", note_id="one", midi=60, start=0, end=.5, **fields)


def test_add_to_empty_score_delete_split_and_merge_preserve_history():
    empty = SongScore(song=SongInfo(duration_seconds=4))
    added = apply(empty, "add", midi=61, start=0.3, end=1.3).score
    original_note = added.melody[0]
    assert original_note.confidence == 0
    assert not added.melody_edits[0].before
    split = apply(added, "split", note_id=original_note.id, split_time=0.8).score
    assert len(split.melody) == 2
    assert split.melody[0].end == split.melody[1].start == 0.8
    merged = apply(split, "merge_next", note_id=original_note.id).score
    assert len(merged.melody) == 1
    assert (merged.melody[0].start, merged.melody[0].end) == (0.3, 1.3)
    deleted = apply(merged, "delete", note_id=original_note.id).score
    assert not deleted.melody
    assert len(deleted.melody_edits) == 4
    assert deleted.melody_edits[-1].before[0].midi == 61
    assert deleted.melody_edits[-1].after == []


@pytest.mark.parametrize("fields", [
    {"start": 1, "end": 1.2}, {"start": 0.2, "end": 0.1},
    {"start": 3, "end": 5}, {"start": 0, "end": 0.001},
    {"start": float("nan"), "end": 0.5}, {"midi": 128}, {"midi": 60.5},
])
def test_invalid_edits_are_rejected_without_mutation(fields):
    original = score()
    before = original.model_dump_json()
    values = {"note_id": "one", "midi": 60, "start": 0, "end": 0.5, **fields}
    with pytest.raises(ValueError):
        apply(original, "update", **values)
    assert original.model_dump_json() == before


def test_merge_does_not_fill_rests_or_merge_different_pitches():
    with pytest.raises(ValueError):
        apply(score(), "merge_next", note_id="one")
    with pytest.raises(ValueError):
        apply(score(), "split", note_id="one", split_time=0.5)
    with pytest.raises(ValueError):
        apply(score(), "delete", note_id="missing")


def test_unplayable_pitch_is_retained_without_stale_fingering():
    result = apply(score(), "update", note_id="one", midi=20, start=0, end=0.5).score
    assert result.melody[0].midi == 20
    assert result.melody[0].string is None and result.melody[0].fret is None


def test_custom_tuning_and_capo_are_used_for_edited_tab():
    original = score()
    original.guitar.tuning = [38, 45, 50, 55, 59, 64]
    original.analysis.capo = original.guitar.capo = 2
    result = apply(original, "update", note_id="one", midi=40, start=0, end=0.5).score
    assert (result.melody[0].string, result.melody[0].fret) == (6, 0)


def test_shift_phrase_preserves_spacing_duration_fingering_and_outside_events(tmp_path):
    original = score()
    original.song.duration_seconds = 8
    original.melody[0].start, original.melody[0].end = .5, 1
    original.melody[1].start, original.melody[1].end = 1.5, 2.5
    original.melody.append(MelodyNote(id="outside", start=4, end=5, midi=64, note="E4", confidence=.2))
    source = original.model_dump_json()
    result = apply(original, "shift_phrase", range_start=0, range_end=2, target_start=0).score
    for before, after in zip(original.melody[:2], result.melody[:2]):
        assert after.start == pytest.approx(before.start - .5)
        assert after.end - after.start == pytest.approx(before.end - before.start)
        assert (after.midi, after.string, after.fret, after.confidence, after.source_midi) == (before.midi, before.string, before.fret, before.confidence, before.source_midi)
    assert result.melody[1].start - result.melody[0].end == .5
    assert result.melody[2] == original.melody[2]
    assert original.model_dump_json() == source
    assert result.beats == original.beats and result.chords == original.chords
    assert result.melody_edits[-1].operation == "shift_phrase"
    assert len(result.melody_edits[-1].before) == 2
    events = {event.source_id: event for event in compile_playback_manifest(result).events}
    assert events["one"].start == 0 and events["two"].end == 2
    store = RevisionStore(tmp_path)
    saved = store.save(result)
    assert store.load(saved) == result


@pytest.mark.parametrize("start,end,target", [(0, 4, 0), (0, 4, 1.5), (2, 1, 0), (1.6, 4, 1.6), (3, 4, 3)])
def test_shift_phrase_rejects_invalid_empty_carried_or_excessive_moves(start, end, target):
    original = score()
    original.analysis.bpm = 240  # one 4/4 bar is one second
    original.melody = [MelodyNote(id="a", start=1.5, end=2.5, midi=60, note="C4", confidence=.5)]
    with pytest.raises(ValueError):
        apply(original, "shift_phrase", range_start=start, range_end=end, target_start=target)


def test_shift_phrase_uses_detected_bar_duration_for_strict_less_than_one_bar():
    from app.models.analysis import BeatInfo
    original = score()
    original.melody = [MelodyNote(id="a", start=1, end=1.2, midi=60, note="C4", confidence=.5)]
    original.beats = [BeatInfo(time=0, beat=1, measure=1, confidence=1), BeatInfo(time=1, beat=1, measure=2, confidence=1), BeatInfo(time=2, beat=1, measure=3, confidence=1)]
    with pytest.raises(ValueError, match="小於"):
        apply(original, "shift_phrase", range_start=0, range_end=2, target_start=0)
    result = apply(original, "shift_phrase", range_start=0, range_end=2, target_start=.1).score
    assert result.melody[0].start == pytest.approx(.1)


def test_playback_midi_musicxml_and_revision_use_edited_notes(tmp_path):
    original = score()
    result = apply(original, "update", note_id="one", midi=64, start=0.1, end=0.75).score
    event = next(e for e in compile_playback_manifest(result).events if e.source_id == "one")
    assert event.pitches == (64,) and event.start == 0.1 and event.end == 0.75
    assert bytes([0x90, 64, 96]) in export_midi(result)
    xml = ElementTree.fromstring(export_musicxml(result))
    assert xml.find(".//pitch/step").text == "E"
    assert xml.findtext(".//note[pitch]/duration") == "624"
    store = RevisionStore(tmp_path)
    parent = store.save(original)
    child = store.fork(parent, result)
    assert store.load(parent) == original
    assert store.load(child) == result


@pytest.mark.asyncio
async def test_edit_endpoint_and_new_revision_do_not_replace_parent(tmp_path):
    from app.api import app, get_revision_store
    store = RevisionStore(tmp_path)
    app.dependency_overrides[get_revision_store] = lambda: store
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            original = score().model_dump(mode="json")
            edited = await client.post("/scores/melody/edit", json={"score": original, "operation": "update", "note_id": "one", "midi": 65, "start": 0, "end": 0.8})
            assert edited.status_code == 200
            result = edited.json()["score"]
            parent = (await client.post("/revisions", json={"score": original})).json()["revision_id"]
            child = (await client.post("/revisions", json={"score": result, "revision_id": parent, "create_new": True})).json()["revision_id"]
            assert child != parent
            assert (await client.get(f"/revisions/{parent}")).json()["melody"][0]["midi"] == 60
            assert (await client.get(f"/revisions/{child}")).json()["melody"][0]["midi"] == 65
            failed = await client.post("/scores/melody/edit", json={"score": result, "operation": "add", "midi": 62, "start": 0.2, "end": 0.3})
            assert failed.status_code == 422
    finally:
        app.dependency_overrides.clear()
