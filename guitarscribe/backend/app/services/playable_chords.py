"""Attach default guitar shapes without changing harmonic analysis or edits."""

from ..models.score import SongScore
from .voicings import ChordVoicingProvider


def with_default_voicings(score: SongScore) -> SongScore:
    result = score.model_copy(deep=True)
    provider = ChordVoicingProvider()
    for chord in result.chords:
        if chord.available_voicings or chord.symbol.strip().lower() in {"n", "nc", "n.c.", "no_chord"}:
            continue
        chord.available_voicings = provider.get(
            chord.shape_symbol or chord.symbol,
            capo=result.analysis.capo,
            max_fret=result.guitar.max_fret,
        )
        chord.voicing_id = chord.available_voicings[0].id if chord.available_voicings else None
    return result
