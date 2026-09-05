from typing import List
from ..models.analysis import BeatInfo, MelodyNote

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

    def quantize_to_beats(self, notes: List[MelodyNote], beats: List[BeatInfo]) -> List[MelodyNote]:
        if len(beats) < 2:
            return notes
        grid = [beat.time for beat in beats]
        grid.extend((left.time + right.time) / 2 for left, right in zip(beats, beats[1:]))
        grid.sort()
        for note in notes:
            start = min(grid, key=lambda point: abs(point - note.start))
            end = min(grid, key=lambda point: abs(point - note.end))
            note.start = start
            note.end = end if end > start else start + 0.05
        return notes

    def process(self, notes: List[MelodyNote], beats: List[BeatInfo] | None = None) -> List[MelodyNote]:
        notes = self.remove_short_notes(notes)
        notes = self.remove_low_confidence(notes)
        notes = self.merge_repeated(notes)
        return self.quantize_to_beats(notes, beats) if beats else notes
