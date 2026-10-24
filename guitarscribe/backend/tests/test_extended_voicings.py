import pytest

from app.services.voicings import ChordVoicingProvider


ROOTS = {"C": 0, "C#": 1, "D": 2, "Eb": 3, "E": 4, "F": 5,
         "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
INTERVALS = {"7": {0, 4, 7, 10}, "maj7": {0, 4, 7, 11}, "m7": {0, 3, 7, 10},
             "6": {0, 4, 7, 9}, "m6": {0, 3, 7, 9}, "m7b5": {0, 3, 6, 10}}
TUNING = [40, 45, 50, 55, 59, 64]


@pytest.mark.parametrize("root", ROOTS)
@pytest.mark.parametrize("quality", INTERVALS)
def test_all_roots_have_complete_extended_shapes_without_foreign_tones(root, quality):
    voicings = ChordVoicingProvider().get(root + quality, max_fret=15)
    assert voicings
    assert all("incomplete" not in v.tags for v in voicings)
    for voicing in voicings:
        actual = {(pitch + fret) % 12 for pitch, fret in zip(TUNING, voicing.frets) if fret is not None}
        assert actual == {(ROOTS[root] + interval) % 12 for interval in INTERVALS[quality]}
        assert all(fret is None or 0 <= fret <= 15 for fret in voicing.frets)


@pytest.mark.parametrize("max_fret", [0, 2, 5, 9, 12])
def test_max_fret_is_respected_including_when_only_root_fallback_fits(max_fret):
    for root in ROOTS:
        for quality in INTERVALS:
            for voicing in ChordVoicingProvider().get(root + quality, max_fret=max_fret):
                assert max(fret for fret in voicing.frets if fret is not None) <= max_fret
                if "incomplete" not in voicing.tags:
                    assert {(pitch + fret) % 12 for pitch, fret in zip(TUNING, voicing.frets)
                            if fret is not None} == {(ROOTS[root] + interval) % 12 for interval in INTERVALS[quality]}


def test_existing_triad_order_and_unknown_quality_remain_explicit():
    provider = ChordVoicingProvider()
    assert [v.id for v in provider.get("C")][:2] == ["open-c", "barre-c-3"]
    assert provider.get("Am")[0].id == "open-am"
    for symbol in ("Cunknown", "C9", "Csus4"):
        assert all("incomplete" in v.tags and "root-note" in v.tags for v in provider.get(symbol))


def test_capo_is_metadata_and_does_not_change_shape_pitch_classes():
    provider = ChordVoicingProvider()
    assert [v.frets for v in provider.get("G7", capo=3)] == [v.frets for v in provider.get("G7")]
    assert all(v.capo == 3 for v in provider.get("G7", capo=3))
