from typing import List
from ..models.analysis import MelodyNote

class MelodyPostProcessor:
    def remove_short_notes(self, notes: List[MelodyNote], min_duration: float = 0.08) -> List[MelodyNote]:
        return [n for n in notes if n.end - n.start >= min_duration]

    def remove_low_confidence(self, notes: List[MelodyNote], min_confidence: float = 0.4) -> List[MelodyNote]:
        return [n for n in notes if n.confidence >= min_confidence]

    def merge_repeated(self, notes: List[MelodyNote], pitch_tolerance: int = 0) -> List[MelodyNote]:
        if not notes:
            return []
            
        merged = [notes[0]]
        for note in notes[1:]:
            last = merged[-1]
            if abs(note.midi - last.midi) <= pitch_tolerance and (note.start - last.end) < 0.1:
                last.end = max(last.end, note.end)
                last.confidence = max(last.confidence, note.confidence)
            else:
                merged.append(note)
        return merged

    def process(self, notes: List[MelodyNote]) -> List[MelodyNote]:
        notes = self.remove_short_notes(notes)
        notes = self.remove_low_confidence(notes)
        notes = self.merge_repeated(notes)
        return notes
