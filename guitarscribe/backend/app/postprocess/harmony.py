"""Conservative functional-harmony context for chord sequence decoding."""

from __future__ import annotations

import re

from ..models.analysis import ChordEvent


ROOT_PITCH = {
    "C": 0, "B#": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4, "E#": 5, "F": 5, "F#": 6, "Gb": 6, "G": 7,
    "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11,
}
CHORD_RE = re.compile(r"^([A-G](?:#|b)?)(.*)$")
MAJOR_INTERVALS = (0, 2, 4, 5, 7, 9, 11)
MINOR_INTERVALS = (0, 2, 3, 5, 7, 8, 10)
MAJOR_QUALITIES = ("major", "minor", "minor", "major", "major", "minor", "diminished")
MINOR_QUALITIES = ("minor", "diminished", "major", "minor", "major", "major", "major")
ROMAN_UPPER = ("I", "II", "III", "IV", "V", "VI", "VII")
ROMAN_LOWER = ("i", "ii", "iii", "iv", "v", "vi", "vii")


def parse_chord(symbol: str) -> tuple[str, int, str] | None:
    match = CHORD_RE.match(symbol.strip().split("/", 1)[0])
    if not match:
        return None
    root, suffix = match.groups()
    suffix = suffix.lower().lstrip(":")
    if suffix.startswith("dim") or suffix.startswith("°"):
        quality = "diminished"
    elif suffix.startswith("aug") or suffix.startswith("+"):
        quality = "augmented"
    elif (suffix.startswith("m") and not suffix.startswith("maj")) or suffix.startswith("min"):
        quality = "minor"
    elif suffix.startswith("7") or suffix.startswith("dom"):
        quality = "dominant"
    else:
        quality = "major"
    return root, ROOT_PITCH[root], quality


def _scale(key: str, mode: str) -> tuple[list[int], tuple[str, ...]]:
    tonic = ROOT_PITCH.get(key, 0)
    intervals = MINOR_INTERVALS if mode.lower().startswith("min") else MAJOR_INTERVALS
    qualities = MINOR_QUALITIES if mode.lower().startswith("min") else MAJOR_QUALITIES
    return [((tonic + interval) % 12) for interval in intervals], qualities


def _roman(degree: int, quality: str) -> str:
    numeral = ROMAN_LOWER[degree] if quality in {"minor", "diminished"} else ROMAN_UPPER[degree]
    return numeral + ("°" if quality == "diminished" else "+" if quality == "augmented" else "")


def _function_for_degree(degree: int, mode: str) -> str:
    if mode.lower().startswith("min"):
        if degree in {0, 2}:
            return "tonic"
        if degree in {1, 3, 5}:
            return "predominant"
        return "dominant"
    if degree in {0, 2, 5}:
        return "tonic"
    if degree in {1, 3}:
        return "predominant"
    return "dominant"


def _secondary_dominant_target(
    chord: ChordEvent, next_chord: ChordEvent | None, scale: list[int], qualities: tuple[str, ...]
) -> str | None:
    current = parse_chord(chord.symbol)
    following = parse_chord(next_chord.symbol) if next_chord else None
    if not current or not following or current[2] not in {"major", "dominant"}:
        return None
    if (current[1] + 5) % 12 != following[1] or following[1] not in scale:
        return None
    degree = scale.index(following[1])
    if degree == 0:
        return None
    return _roman(degree, qualities[degree])


def apply_harmonic_context(
    chords: list[ChordEvent], key: str, mode: str, correction_threshold: float = 0.6
) -> list[ChordEvent]:
    """Annotate function and correct only weak parallel major/minor mistakes."""
    scale, qualities = _scale(key, mode)
    for index, chord in enumerate(chords):
        parsed = parse_chord(chord.symbol)
        if not parsed:
            chord.harmonic_function = "unknown"
            chord.theory_confidence = 0.0
            continue
        root_name, root_pitch, quality = parsed
        next_chord = chords[index + 1] if index + 1 < len(chords) else None
        secondary_target = _secondary_dominant_target(chord, next_chord, scale, qualities)
        if secondary_target:
            chord.roman_numeral = f"V/{secondary_target}"
            chord.harmonic_function = "secondary_dominant"
            chord.theory_confidence = 0.9
            continue
        if root_pitch not in scale:
            chord.harmonic_function = "chromatic"
            chord.theory_confidence = 0.35
            continue

        degree = scale.index(root_pitch)
        expected = qualities[degree]
        # In minor, both a minor v and harmonic-minor major/dominant V are valid.
        valid_quality = (
            quality == expected
            or (degree == 4 and quality == "dominant")
            or (mode.lower().startswith("min") and degree == 4 and quality in {"major", "minor", "dominant"})
        )
        if not valid_quality and chord.confidence < correction_threshold and quality in {"major", "minor"}:
            if chord.detected_symbol is None:
                chord.detected_symbol = chord.symbol
            chord.symbol = root_name + ("m" if expected == "minor" else "dim" if expected == "diminished" else "")
            chord.origin = "theory"
            quality = expected
            valid_quality = True

        chord.roman_numeral = _roman(degree, quality)
        chord.harmonic_function = _function_for_degree(degree, mode) if valid_quality else "modal_mixture"
        chord.theory_confidence = 0.85 if valid_quality else 0.55
    return chords
