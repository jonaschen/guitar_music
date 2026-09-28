"""Experimental stem-candidate reranking; not enabled in production playback."""

from ..models.analysis import MelodyNote


def pitch_support(note: MelodyNote, reference: list[MelodyNote], min_confidence: float = 0.6) -> float:
    """Exact-register agreement over raw event time, using interval union."""
    if note.end <= note.start:
        return 0.0
    intervals = sorted((max(note.start, ref.start), min(note.end, ref.end)) for ref in reference
                       if ref.midi == note.midi and ref.confidence >= min_confidence
                       and ref.start < note.end and ref.end > note.start)
    covered, cursor = 0.0, note.start
    for start, end in intervals:
        covered += max(0.0, end - max(start, cursor))
        cursor = max(cursor, end)
    return covered / (note.end - note.start)


def rerank_with_reference(raw: list[MelodyNote], quantized: list[MelodyNote],
                          selected: list[MelodyNote], reference: list[MelodyNote]) -> tuple[list[MelodyNote], list[dict]]:
    """Only replace a selected event with a corroborated existing alternative.

    Exact pitch must cover >= half of the raw candidate, exceed old support
    by >= 0.25, and have reference confidence >= 0.6. These experimental
    safeguards are not calibrated accuracy thresholds. Absence of support
    never deletes a primary event. No key/scale or reference-score correction.
    """
    originals = {note.id: note for note in raw}
    buckets: dict[float, list[MelodyNote]] = {}
    for note in quantized:
        buckets.setdefault(round(note.start, 4), []).append(note)
    result, decisions = [], []
    for chosen in selected:
        def support(candidate):
            original = originals.get(candidate.id)
            return pitch_support(original, reference) if original else 0.0
        old_support = support(chosen)
        alternatives = [candidate for candidate in buckets.get(round(chosen.start, 4), [])
                        if candidate.id in originals and candidate.midi != chosen.midi
                        and 48 <= candidate.midi <= 84]
        alternatives.sort(key=lambda candidate: (-support(candidate), candidate.id))
        winner = alternatives[0] if alternatives else None
        if winner and support(winner) >= 0.5 and support(winner) - old_support >= 0.25:
            decisions.append({"start": chosen.start, "old_id": chosen.id, "new_id": winner.id,
                              "old_midi": chosen.midi, "new_midi": winner.midi,
                              "old_support": old_support, "new_support": support(winner)})
            result.append(winner.model_copy(deep=True))
        else:
            result.append(chosen.model_copy(deep=True))
    return result, decisions
