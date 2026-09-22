from ..models.analysis import ChordVoicing
from ..models.score import SongScore
from .voicings import ChordVoicingProvider


STANDARD_TUNING_MIDI = (40, 45, 50, 55, 59, 64)


class SongVoicingOptimizer:
    """Choose a playable voicing path with sequence-level voice leading."""

    def __init__(self, provider: ChordVoicingProvider | None = None):
        self.provider = provider or ChordVoicingProvider()

    @staticmethod
    def _sounding_pitches(voicing: ChordVoicing) -> set[int]:
        return {
            tuning + fret + voicing.capo
            for tuning, fret in zip(STANDARD_TUNING_MIDI, voicing.frets)
            if fret is not None
        }

    @classmethod
    def transition_cost(cls, previous: ChordVoicing, current: ChordVoicing) -> float:
        """Estimate hand motion while rewarding pitches that can keep ringing."""
        shared_strings = [
            (left, right)
            for left, right in zip(previous.frets, current.frets)
            if left is not None and right is not None
        ]
        average_fret_motion = (
            sum(abs(left - right) for left, right in shared_strings) / len(shared_strings)
            if shared_strings else 6.0
        )
        retained_on_string = sum(left == right for left, right in shared_strings)
        changed_string_use = sum(
            (left is None) != (right is None)
            for left, right in zip(previous.frets, current.frets)
        )
        retained_pitches = len(cls._sounding_pitches(previous) & cls._sounding_pitches(current))
        previous_bass = min(cls._sounding_pitches(previous), default=40)
        current_bass = min(cls._sounding_pitches(current), default=40)
        return (
            abs(previous.base_fret - current.base_fret) * 0.18
            + average_fret_motion * 0.08
            + changed_string_use * 0.08
            + abs(previous_bass - current_bass) * 0.025
            - retained_on_string * 0.12
            - retained_pitches * 0.05
        )

    @classmethod
    def _optimize_segment(cls, candidate_sets: list[list[ChordVoicing]]) -> list[ChordVoicing]:
        costs = [candidate.difficulty for candidate in candidate_sets[0]]
        backpointers: list[list[int]] = []
        for candidates in candidate_sets[1:]:
            previous_candidates = candidate_sets[len(backpointers)]
            next_costs: list[float] = []
            pointers: list[int] = []
            for candidate in candidates:
                options = [
                    cost + cls.transition_cost(previous, candidate)
                    for cost, previous in zip(costs, previous_candidates)
                ]
                best_previous = min(range(len(options)), key=options.__getitem__)
                next_costs.append(options[best_previous] + candidate.difficulty)
                pointers.append(best_previous)
            costs = next_costs
            backpointers.append(pointers)

        state = min(range(len(costs)), key=costs.__getitem__)
        states = [state]
        for pointers in reversed(backpointers):
            state = pointers[state]
            states.append(state)
        states.reverse()
        return [candidates[state] for candidates, state in zip(candidate_sets, states)]

    def optimize(self, score: SongScore) -> SongScore:
        result = score.model_copy(deep=True)
        segment_chords = []
        segment_candidates: list[list[ChordVoicing]] = []

        def apply_segment() -> None:
            if not segment_candidates:
                return
            for chord, selected in zip(segment_chords, self._optimize_segment(segment_candidates)):
                chord.voicing_id = selected.id
            segment_chords.clear()
            segment_candidates.clear()

        for chord in result.chords:
            symbol = chord.shape_symbol or chord.symbol
            candidates = self.provider.get(symbol, capo=result.analysis.capo)
            chord.available_voicings = candidates
            if not candidates:
                apply_segment()
                continue
            segment_chords.append(chord)
            segment_candidates.append(candidates)
        apply_segment()
        return result
