from app.models.analysis import ChordEvent
from app.postprocess.harmony import apply_harmonic_context, tonal_bias


def chord(symbol: str, confidence: float = 0.8) -> ChordEvent:
    return ChordEvent(id=symbol, start=0, end=1, symbol=symbol, confidence=confidence)


def test_major_key_assigns_roman_numerals_and_functions():
    chords = [chord("C"), chord("Dm"), chord("G7"), chord("Am")]

    apply_harmonic_context(chords, "C", "major")

    assert [(item.roman_numeral, item.harmonic_function) for item in chords] == [
        ("I", "tonic"), ("ii", "predominant"), ("V", "dominant"), ("vi", "tonic"),
    ]


def test_low_confidence_parallel_quality_is_corrected_but_source_is_preserved():
    chords = [chord("D", 0.45), chord("F", 0.8), chord("C", 0.8)]

    apply_harmonic_context(chords, "C", "major")

    assert chords[0].symbol == "Dm"
    assert chords[0].detected_symbol == "D"
    assert chords[0].source_symbol is None
    assert chords[0].origin == "theory"
    assert chords[0].roman_numeral == "ii"


def test_high_confidence_modal_mixture_is_annotated_without_rewriting():
    chords = [chord("Fm", 0.9), chord("C", 0.9)]

    apply_harmonic_context(chords, "C", "major")

    assert chords[0].symbol == "Fm"
    assert chords[0].roman_numeral == "iv"
    assert chords[0].harmonic_function == "modal_mixture"


def test_secondary_dominant_resolution_is_not_forced_back_into_key():
    chords = [chord("A7", 0.45), chord("Dm", 0.8), chord("G7", 0.8), chord("C", 0.8)]

    apply_harmonic_context(chords, "C", "major")

    assert chords[0].symbol == "A7"
    assert chords[0].roman_numeral == "V/ii"
    assert chords[0].harmonic_function == "secondary_dominant"


def test_minor_key_accepts_harmonic_minor_dominant():
    chords = [chord("Dm"), chord("E7"), chord("Am")]

    apply_harmonic_context(chords, "A", "minor")

    assert chords[1].symbol == "E7"
    assert chords[1].roman_numeral == "V"
    assert chords[1].harmonic_function == "dominant"


def test_tonal_bias_is_weak_and_does_not_forbid_borrowed_chords():
    assert tonal_bias("Dm", "C", "major") > tonal_bias("D", "C", "major")
    assert tonal_bias("Bb", "C", "major") == -0.01
    assert tonal_bias("N", "C", "major") == 0.0
