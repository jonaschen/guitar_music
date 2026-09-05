from ..models.score import SongScore
from .voicings import ChordVoicingProvider


class SongVoicingOptimizer:
    """Greedy MVP optimizer balancing intrinsic difficulty and fretboard movement."""

    def __init__(self, provider: ChordVoicingProvider | None = None):
        self.provider = provider or ChordVoicingProvider()

    def optimize(self, score: SongScore) -> SongScore:
        result = score.model_copy(deep=True)
        previous_position: int | None = None
        for chord in result.chords:
            symbol = chord.shape_symbol or chord.symbol
            candidates = self.provider.get(symbol, capo=result.analysis.capo)
            chord.available_voicings = candidates
            if not candidates:
                continue
            def cost(candidate):
                movement = 0 if previous_position is None else abs(candidate.base_fret - previous_position) * 0.35
                return candidate.difficulty + movement
            selected = min(candidates, key=cost)
            chord.voicing_id = selected.id
            previous_position = selected.base_fret
        return result
