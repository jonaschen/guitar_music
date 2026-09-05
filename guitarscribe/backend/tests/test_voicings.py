from app.services.voicings import ChordVoicingProvider


def test_common_open_voicing_is_available():
    voicings = ChordVoicingProvider().get("G", capo=2)
    assert voicings[0].id == "open-g"
    assert voicings[0].capo == 2
    assert len(voicings) == 4
    assert voicings[1].base_fret == 3


def test_unknown_chord_gets_a_playable_root_note_fallback():
    voicings = ChordVoicingProvider().get("Cmaj9")
    assert voicings[0].id == "root-note-Cmaj9"
    assert "incomplete" in voicings[0].tags


def test_too_high_voicing_returns_empty_list():
    assert ChordVoicingProvider().get("G", max_fret=2) == []


def test_closed_major_and_minor_shapes_are_available():
    major_tags = {tag for voicing in ChordVoicingProvider().get("Bb") for tag in voicing.tags}
    minor_tags = {tag for voicing in ChordVoicingProvider().get("F#m") for tag in voicing.tags}
    assert {"e-shape", "a-shape"} <= major_tags
    assert {"e-shape", "a-shape"} <= minor_tags
