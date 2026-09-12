from ..models.analysis import MelodyAnalysis, MelodyNote

class SimpleFretboardMapper:
    def __init__(self):
        # E2, A2, D3, G3, B3, E4
        self.string_tuning = [40, 45, 50, 55, 59, 64]
        
    def candidates(self, note: MelodyNote, capo: int = 0, max_fret: int = 12):
        """Return physical fret positions for a sounding MIDI note.

        A capo raises every open-string pitch, so it must be considered when
        producing the displayed fret number.  The number remains relative to
        the capo, as guitar tab convention expects.
        """
        return [
            (6 - index, note.midi - tuning - capo)
            for index, tuning in enumerate(self.string_tuning)
            if 0 <= note.midi - tuning - capo <= max_fret
        ]

    def map_notes(self, melody: MelodyAnalysis, capo: int = 0, max_fret: int = 12, preference: str = "balanced") -> MelodyAnalysis:
        mapped = []
        previous = None
        for note in melody.notes:
            candidates = self.candidates(note, capo, max_fret)
            def cost(candidate):
                string, fret = candidate
                intrinsic = fret * (0.45 if preference == "low_position" else 0.1)
                if previous is None:
                    return intrinsic
                movement = abs(fret - previous[1])
                string_change = 2.5 if preference == "single_string" and string != previous[0] else 0.75 if string != previous[0] else 0
                return intrinsic + movement + string_change
            choice = min(candidates, key=cost) if candidates else None
            mapped.append(note.model_copy(update={"string": choice[0], "fret": choice[1]}) if choice else note.model_copy(update={"string": None, "fret": None}))
            previous = choice
        melody.notes = mapped
        return melody
