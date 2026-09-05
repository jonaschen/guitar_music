from pydantic import BaseModel

from ..models.analysis import AccidentalPreference
from ..models.score import SongScore
from .transposition import TranspositionService
from .voicings import ChordVoicingProvider


class CapoRecommendation(BaseModel):
    capo: int
    shape_key: str
    difficulty: float
    open_chords: int
    barre_chords: int
    covered_chords: int


class CapoAdvisor:
    def __init__(self):
        self.transposition = TranspositionService()
        self.voicings = ChordVoicingProvider()

    def recommend(self, score: SongScore, max_capo: int = 8) -> list[CapoRecommendation]:
        symbols = [chord.symbol for chord in score.chords]
        target_key = score.key_context.target.key
        preference = score.key_context.accidental_preference
        result = []
        for capo in range(max_capo + 1):
            shapes = [self.transposition.transpose_chord_symbol(symbol, -capo, preference, score.analysis.mode) for symbol in symbols]
            candidates = [self.voicings.get(shape, capo=capo) for shape in shapes]
            covered = sum(bool(options) for options in candidates)
            selected = [min(options, key=lambda item: item.difficulty) for options in candidates if options]
            open_count = sum("open" in voicing.tags for voicing in selected)
            barre_count = sum("barre" in voicing.tags for voicing in selected)
            penalty = len(symbols) - covered
            difficulty = round((sum(voicing.difficulty for voicing in selected) + penalty * 5) / max(len(symbols), 1), 2)
            result.append(CapoRecommendation(
                capo=capo,
                shape_key=self.transposition.transpose_note_name(target_key, -capo, preference, score.analysis.mode),
                difficulty=difficulty,
                open_chords=open_count,
                barre_chords=barre_count,
                covered_chords=covered,
            ))
        return sorted(result, key=lambda item: (item.difficulty, -item.open_chords, item.capo))
