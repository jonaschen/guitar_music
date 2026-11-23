from pydantic import BaseModel

from ..models.score import SongScore
from .transposition import TranspositionService
from .voicings import ChordVoicingProvider
from .voicing_optimizer import SongVoicingOptimizer, STANDARD_TUNING_MIDI


class CapoRecommendation(BaseModel):
    capo: int
    shape_key: str
    difficulty: float
    open_chords: int
    barre_chords: int
    covered_chords: int
    total_chords: int
    transition_cost: float
    position_penalty: float
    ranking_score: float
    voicing_plan: dict[str, str]


class CapoAdvisor:
    def __init__(self):
        self.transposition = TranspositionService()
        self.voicings = ChordVoicingProvider()

    def recommend(self, score: SongScore, max_capo: int = 8, preferred_fret: int | None = None) -> list[CapoRecommendation]:
        if tuple(score.guitar.tuning) != STANDARD_TUNING_MIDI:
            raise ValueError('目前 Capo 建議只支援標準調弦 EADGBE，原譜未修改。')
        if preferred_fret is not None and (type(preferred_fret) is not int or not 0 <= preferred_fret <= score.guitar.max_fret):
            raise ValueError('偏好把位需在 0 與目前最高琴格之間。')
        chords = sorted(score.chords, key=lambda chord: chord.start)
        total = sum(chord.symbol != 'N.C.' for chord in chords)
        if not total:
            return []
        target_key = score.key_context.target.key
        preference = score.key_context.accidental_preference
        result = []
        def position_cost(voicing):
            if preferred_fret is None: return 0.0
            hand_fret = min((f for f in voicing.frets if f not in (None, 0)), default=0)
            return abs(hand_fret-preferred_fret) * .08
        def transition(left, right):
            # Existing voice-leading heuristic, bounded below by no movement.
            return max(0.0, SongVoicingOptimizer.transition_cost(left, right))
        for capo in range(min(max_capo, score.guitar.max_capo) + 1):
            selected, segment, segment_ids = [], [], []
            plan = {}
            movement = 0.0
            def finish_segment():
                nonlocal movement
                if not segment: return
                path = SongVoicingOptimizer._optimize_segment(segment,
                    intrinsic_cost=lambda v: v.difficulty+position_cost(v), transition_cost=transition)
                movement += sum(transition(a,b) for a,b in zip(path,path[1:]))
                plan.update((identifier, v.id) for identifier,v in zip(segment_ids,path))
                selected.extend(path); segment.clear(); segment_ids.clear()
            previous_end = None
            for chord in chords:
                if previous_end is not None and chord.start > previous_end + .001: finish_segment()
                previous_end = chord.end
                if chord.symbol == 'N.C.': finish_segment(); continue
                shape = self.transposition.transpose_chord_symbol(chord.symbol, -capo, preference, score.analysis.mode)
                options = [v for v in self.voicings.get(shape, capo=capo, max_fret=score.guitar.max_fret)
                           if 'incomplete' not in v.tags and 'root-note' not in v.tags]
                if options: segment.append(options); segment_ids.append(chord.id)
                else: finish_segment()
            finish_segment()
            covered = len(selected)
            open_count = sum("open" in voicing.tags for voicing in selected)
            barre_count = sum("barre" in voicing.tags for voicing in selected)
            difficulty = (sum(voicing.difficulty for voicing in selected) + (total-covered)*5) / total
            position = sum(position_cost(v) for v in selected) / total
            movement /= total
            result.append(CapoRecommendation(
                capo=capo,
                shape_key=self.transposition.transpose_note_name(target_key, -capo, preference, score.analysis.mode),
                difficulty=round(difficulty, 2),
                open_chords=open_count,
                barre_chords=barre_count,
                covered_chords=covered,
                total_chords=total, transition_cost=round(movement, 3), position_penalty=round(position, 3),
                ranking_score=round(difficulty+movement+position, 3),
                voicing_plan=plan,
            ))
        return sorted(result, key=lambda item: (-item.covered_chords, item.ranking_score, -item.open_chords, item.capo))
