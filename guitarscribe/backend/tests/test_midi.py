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
    assert guitar[0].pitch_offsets == (0.0, 0.012, 0.024, 0.036, 0.048)
    assert guitar[0].pitch_velocities == (98, 96, 94, 92, 90)
    assert guitar[1].pitches == tuple(reversed(guitar[0].pitches))
    assert guitar[1].pitch_offsets == guitar[0].pitch_offsets
    assert guitar[1].pitch_velocities == (86, 84, 82, 80, 78)


def test_midi_export_includes_selected_guitar_voicing_when_melody_is_empty():
    score = SongScore(
        song=SongInfo(duration_seconds=2),
        analysis=AnalysisSummary(bpm=120),
        chords=[ChordEvent(
            id="c1", start=0.0, end=1.0, symbol="C", voicing_id="open-c",
            available_voicings=[ChordVoicing(
                id="open-c", symbol="C", shape_symbol="C",
                frets=[None, 3, 2, 0, 1, 0],
            )],
        )],
        rhythm=RhythmSuggestion(subdivision=8, display=["D"]),
    )

    output = export_midi(score)

    assert bytes([0xC0, 81]) in output
    assert bytes([0xC1, 24]) in output
    assert bytes([0x91, 48, 98]) in output
    assert bytes([0x81, 48, 0]) in output


def test_playback_manifest_compiles_arpeggio_template_with_longer_spread():
    score = SongScore(
        song=SongInfo(duration_seconds=2),
        analysis=AnalysisSummary(bpm=120),
        chords=[ChordEvent(
            id="c1", start=0.0, end=1.0, symbol="C", voicing_id="open-c",
            available_voicings=[ChordVoicing(id="open-c", symbol="C", shape_symbol="C", frets=[None, 3, 2, 0, 1, 0])],
        )],
        rhythm=RhythmSuggestion(subdivision=8, display=["A"]),
    )

    event = next(event for event in compile_playback_manifest(score).events if event.track == "guitar")

    assert event.stroke == "A"
    assert event.pitch_offsets == (0.0, 0.032, 0.064, 0.096, 0.128)
    assert event.pitch_velocities == (78, 76, 74, 72, 70)
    assert event.start + event.pitch_offsets[-1] < event.end


def test_playback_manifest_revision_changes_with_capo():
    score = SongScore(analysis=AnalysisSummary(capo=0))

    original = compile_playback_manifest(score)
    transposed = compile_playback_manifest(score.model_copy(update={"analysis": score.analysis.model_copy(update={"capo": 1})}))

    assert original.revision != transposed.revision
