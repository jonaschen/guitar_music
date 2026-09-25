from app.exporters.midi import compile_playback_manifest, export_midi
from app.models.analysis import BeatInfo, ChordEvent, ChordVoicing, MelodyNote, RhythmSuggestion
from app.models.score import AnalysisSummary, SongInfo, SongScore


def test_missing_voicings_produce_guitar_without_mutating_saved_score():
    score = SongScore(
        song=SongInfo(duration_seconds=3),
        analysis=AnalysisSummary(bpm=120, capo=2),
        chords=[ChordEvent(id="c", start=0, end=1, symbol="C"),
                ChordEvent(id="n", start=1, end=2, symbol="N"),
                ChordEvent(id="g", start=2, end=3, symbol="G")],
        rhythm=RhythmSuggestion(subdivision=8, display=["D"]),
    )
    original = score.model_dump_json()
    manifest = compile_playback_manifest(score)
    guitar = [event for event in manifest.events if event.track == "guitar"]
    assert {event.source_id for event in guitar} == {"c", "g"}
    assert guitar[0].pitches == (50, 54, 57, 62, 66)
    assert all(event.end <= 1 or event.start >= 2 for event in guitar)
    assert bytes([0x91, 50, 98]) in export_midi(score)
    assert score.model_dump_json() == original


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
        rhythm=RhythmSuggestion(subdivision=8, display=["D", "U"], accents=[1, 1]),
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


def test_rhythm_follows_local_beats_instead_of_restarting_at_regions():
    score = SongScore(
        song=SongInfo(duration_seconds=2), analysis=AnalysisSummary(bpm=120),
        beats=[BeatInfo(time=time, beat=index + 1, measure=1)
               for index, time in enumerate([0, 0.55, 1.15, 1.7])],
        chords=[ChordEvent(id="c1", start=0, end=0.6, symbol="C"),
                ChordEvent(id="c2", start=0.6, end=1.2, symbol="C"),
                ChordEvent(id="g", start=1.2, end=2, symbol="G")],
        rhythm=RhythmSuggestion(subdivision=4, display=["D", "U"]),
    )
    before = score.model_dump_json()
    guitar = [e for e in compile_playback_manifest(score).events if e.track == "guitar"]
    assert [e.start for e in guitar] == [0, 0.55, 1.15, 1.7]
    assert [e.stroke for e in guitar] == ["D", "U", "D", "U"]
    assert guitar[1].end > 0.6  # Same chord's raw region boundary does not cut sound.
    assert guitar[2].end <= 1.2  # Actual harmonic change still cuts the old chord.
    assert score.model_dump_json() == before


def test_no_chord_gap_keeps_pattern_phase_and_short_strums_fit_boundary():
    score = SongScore(
        song=SongInfo(duration_seconds=1), analysis=AnalysisSummary(bpm=120),
        chords=[ChordEvent(id="c", start=0, end=0.01, symbol="C"),
                ChordEvent(id="g", start=0.75, end=1, symbol="G")],
        rhythm=RhythmSuggestion(subdivision=8, display=["D", None, "D", "U"]),
    )
    guitar = [e for e in compile_playback_manifest(score).events if e.track == "guitar"]
    assert [e.start for e in guitar] == [0, 0.75]
    assert [e.stroke for e in guitar] == ["D", "U"]
    assert all(e.start + max(e.pitch_offsets) < e.end for e in guitar)


def test_subdivision_interpolates_beats_and_revision_tracks_timing():
    score = SongScore(
        song=SongInfo(duration_seconds=1), analysis=AnalysisSummary(bpm=120),
        beats=[BeatInfo(time=0, beat=1, measure=1), BeatInfo(time=0.6, beat=2, measure=1)],
        chords=[ChordEvent(id="c", start=0, end=1, symbol="C")],
        rhythm=RhythmSuggestion(subdivision=8, display=["D"]),
    )
    original = compile_playback_manifest(score)
    assert [round(e.start, 3) for e in original.events if e.track == "guitar"] == [0, 0.3, 0.6, 0.85]
    score.beats[1].time = 0.5
    assert compile_playback_manifest(score).revision != original.revision


def test_guitar_rings_across_empty_stroke_slots_but_not_no_chord_gap():
    score = SongScore(
        song=SongInfo(duration_seconds=3), analysis=AnalysisSummary(bpm=120),
        chords=[ChordEvent(id="c", start=0, end=1.5, symbol="C"),
                ChordEvent(id="g", start=2, end=3, symbol="G")],
        rhythm=RhythmSuggestion(subdivision=4, display=["D", None]),
    )
    guitar = [e for e in compile_playback_manifest(score).events if e.track == "guitar"]
    assert [(e.start, e.end) for e in guitar] == [(0, 1), (1, 1.5), (2, 3)]


def test_quarter_note_strums_keep_full_beat_length():
    score = SongScore(
        song=SongInfo(duration_seconds=2), analysis=AnalysisSummary(bpm=120),
        chords=[ChordEvent(id="c", start=0, end=2, symbol="C")],
        rhythm=RhythmSuggestion(subdivision=4, display=["D"]),
    )
    guitar = [e for e in compile_playback_manifest(score).events if e.track == "guitar"]
    assert [(e.start, e.end) for e in guitar] == [(0, 0.5), (0.5, 1), (1, 1.5), (1.5, 2)]
    assert [e.velocity for e in guitar] == [98, 59, 78, 59]


def test_explicit_rhythm_accents_reach_manifest_and_midi():
    score = SongScore(
        song=SongInfo(duration_seconds=2), analysis=AnalysisSummary(bpm=120),
        chords=[ChordEvent(id="c", start=0, end=2, symbol="C")],
        rhythm=RhythmSuggestion(subdivision=4, display=["D"] * 4, accents=[1, 0.5, 0.8, 0.5]),
    )
    manifest = compile_playback_manifest(score)
    guitar = [e for e in manifest.events if e.track == "guitar"]
    assert [e.velocity for e in guitar] == [98, 49, 78, 49]
    assert bytes([0x91, 48, 49]) in export_midi(score)
    score.rhythm.accents = [1] * 4
    assert compile_playback_manifest(score).revision != manifest.revision


def test_pickup_and_measure_reset_control_pattern_phase():
    score = SongScore(
        song=SongInfo(duration_seconds=1.5), analysis=AnalysisSummary(bpm=120),
        beats=[BeatInfo(time=0, beat=4, measure=1), BeatInfo(time=0.5, beat=1, measure=2),
               BeatInfo(time=1, beat=2, measure=2)],
        chords=[ChordEvent(id="c", start=0, end=1.5, symbol="C")],
        rhythm=RhythmSuggestion(subdivision=4, display=["D"] * 4, accents=[1, 0.5, 0.8, 0.5]),
    )
    guitar = [e for e in compile_playback_manifest(score).events if e.track == "guitar"]
    assert [e.velocity for e in guitar] == [49, 98, 49]
    assert len({e.id for e in guitar}) == len(guitar)


def test_reference_repeats_identical_rhythm_each_bar():
    from app.services.playback_reference import reference_score
    manifest = compile_playback_manifest(reference_score())
    guitar = [e for e in manifest.events if e.track == "guitar"]
    assert len(guitar) == 24
    assert len({e.id for e in guitar}) == 24
    for bar in range(4):
        events = [e for e in guitar if bar * 2.5 <= e.start < (bar + 1) * 2.5]
        assert [round(e.start - bar * 2.5, 5) for e in events] == [0, 0.625, 0.9375, 1.5625, 1.875, 2.1875]
        assert events[0].velocity > max(e.velocity for e in events[1:])


def test_mid_bar_chord_changes_do_not_reset_stroke_or_accent():
    from app.services.playback_reference import reference_score
    def attacks(within_bar):
        return [(e.start, e.stroke, e.velocity) for e in compile_playback_manifest(reference_score(within_bar)).events if e.track == "guitar"]
    assert attacks(True) == attacks(False)
