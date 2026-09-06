from app.exporters.midi import compile_playback_manifest, export_midi
from app.models.analysis import BeatInfo, ChordEvent, ChordVoicing, MelodyNote, RhythmSuggestion
from app.models.score import AnalysisSummary, SongInfo, SongScore


def test_midi_export_has_standard_header_and_note_events():
    score = SongScore(
        song=SongInfo(duration_seconds=2),
        analysis=AnalysisSummary(bpm=120),
        melody=[MelodyNote(id="n1", start=0, end=0.5, midi=60, note="C4")],
    )

    output = export_midi(score)

    assert output.startswith(b"MThd\x00\x00\x00\x06")
    assert b"MTrk" in output
    assert bytes([0x90, 60, 96]) in output
    assert bytes([0x80, 60, 0]) in output
    assert output.endswith(bytes([0x8B, 0x20, 0xFF, 0x2F, 0x00]))


def test_playback_manifest_compiles_voicing_capo_melody_and_metronome():
    score = SongScore(
        song=SongInfo(duration_seconds=2),
        analysis=AnalysisSummary(bpm=120, capo=2),
        beats=[BeatInfo(time=0.0, beat=1, measure=1)],
        chords=[ChordEvent(
            id="c1", start=0.0, end=1.0, symbol="C", voicing_id="open-c",
            available_voicings=[ChordVoicing(
                id="open-c", symbol="C", shape_symbol="C",
                frets=[None, 3, 2, 0, 1, 0],
            )],
        )],
        melody=[MelodyNote(id="n1", start=0.0, end=0.5, midi=60, note="C4")],
        rhythm=RhythmSuggestion(subdivision=8, display=["D", "U"]),
    )

    manifest = compile_playback_manifest(score)
    guitar = [event for event in manifest.events if event.track == "guitar"]

    assert {event.track for event in manifest.events} == {"guitar", "melody", "metronome"}
    assert guitar[0].pitches == (50, 54, 57, 62, 66)
    assert guitar[1].pitches == tuple(reversed(guitar[0].pitches))


def test_playback_manifest_revision_changes_with_capo():
    score = SongScore(analysis=AnalysisSummary(capo=0))

    original = compile_playback_manifest(score)
    transposed = compile_playback_manifest(score.model_copy(update={"analysis": score.analysis.model_copy(update={"capo": 1})}))

    assert original.revision != transposed.revision
