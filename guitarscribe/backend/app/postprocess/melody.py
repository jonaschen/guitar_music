from collections import defaultdict
from statistics import median_low
from typing import List
from ..models.analysis import BeatInfo, MelodyMode, MelodyNote

MODE_MIDI_RANGES = {
    MelodyMode.VOCAL: (40, 84),
    MelodyMode.GUITAR: (40, 88),
    MelodyMode.MIX: (36, 88),
}

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
            next_grid = next((point for point in grid if point > start), start + 0.05)
            note.end = end if end > start else next_grid
        return notes

    def select_monophonic_line(self, notes: List[MelodyNote], mode: MelodyMode = MelodyMode.GUITAR) -> List[MelodyNote]:
        """Reduce simultaneous multi-pitch candidates to one playable melody line."""
        buckets: dict[float, list[MelodyNote]] = defaultdict(list)
        for note in notes:
            buckets[round(note.start, 4)].append(note)

        selected: list[MelodyNote] = []
        previous: MelodyNote | None = None
        for start in sorted(buckets):
            candidates = buckets[start]
            minimum_midi, maximum_midi = MODE_MIDI_RANGES[mode]
            playable = [note for note in candidates if minimum_midi <= note.midi <= maximum_midi]
            if not playable:
                continue
            center = float(median_low(note.midi for note in playable))
            choice = min(
                playable,
                key=lambda note: (
                    abs(note.midi - center) * 0.4
                    + (abs(note.midi - previous.midi) * 0.8 if previous else 0)
                    - min(note.end - note.start, 1.0) * 0.2,
                    -note.confidence,
                    note.id,
                ),
            )
            if previous and start - previous.end < 1.5 and abs(choice.midi - previous.midi) > 12:
                continue
            selected.append(choice)
            previous = choice
        return selected

    def process(self, notes: List[MelodyNote], beats: List[BeatInfo] | None = None, mode: MelodyMode = MelodyMode.GUITAR) -> List[MelodyNote]:
        notes = self.remove_short_notes(notes)
        notes = self.remove_low_confidence(notes)
        notes = self.quantize_to_beats(notes, beats) if beats else notes
        notes = self.select_monophonic_line(notes, mode)
        return self.merge_repeated(notes)
