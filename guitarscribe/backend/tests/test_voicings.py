from app.services.voicings import ChordVoicingProvider


def test_common_open_voicing_is_available():
    voicings = ChordVoicingProvider().get("G", capo=2)
    assert voicings[0].id == "open-g"
    assert voicings[0].capo == 2
    assert len(voicings) == 2
    assert voicings[1].base_fret == 3


def test_unknown_or_too_high_voicing_returns_empty_list():
    assert ChordVoicingProvider().get("Cmaj9") == []
    assert ChordVoicingProvider().get("G", max_fret=2) == []
