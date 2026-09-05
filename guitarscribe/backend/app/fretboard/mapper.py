from ..models.analysis import MelodyAnalysis, MelodyNote

class SimpleFretboardMapper:
    def __init__(self):
        # E2, A2, D3, G3, B3, E4
        self.string_tuning = [40, 45, 50, 55, 59, 64]
        
    def candidates(self, note: MelodyNote):
        return [(6 - index, note.midi - tuning) for index, tuning in enumerate(self.string_tuning) if 0 <= note.midi - tuning <= 12]

    def map_notes(self, melody: MelodyAnalysis) -> MelodyAnalysis:
        mapped = []
        previous = None
        for note in melody.notes:
            candidates = self.candidates(note)
            choice = min(candidates, key=lambda candidate: candidate[1] if previous is None else abs(candidate[1] - previous[1]) + (0.75 if candidate[0] != previous[0] else 0)) if candidates else None
            mapped.append(note.model_copy(update={"string": choice[0], "fret": choice[1]}) if choice else note.model_copy(update={"string": None, "fret": None}))
            previous = choice
        melody.notes = mapped
        return melody

        mapped_notes = []
        for note in melody.notes:
            best_string = None
            best_fret = None
            
            # Prefer string 3, 4, 5 (indices 2, 3, 4 in 0-based) for middle
            for string_idx, tuning in reversed(list(enumerate(self.string_tuning))):
                fret = note.midi - tuning
                if 0 <= fret <= 12:
                    # simplistic heuristic: prefer lower fret
                    if best_fret is None or fret < best_fret:
                        best_string = 6 - string_idx
                        best_fret = fret
                        
            new_note = note.model_copy()
            new_note.string = best_string
            new_note.fret = best_fret
            mapped_notes.append(new_note)
            
        melody.notes = mapped_notes
        return melody
