from collections import defaultdict
from math import ceil
from statistics import median_low
from typing import List
from ..models.analysis import BeatInfo, MelodyMode, MelodyNote

MODE_MIDI_RANGES = {
    MelodyMode.VOCAL: (40, 84),
    MelodyMode.GUITAR: (40, 88),
    MelodyMode.MIX: (36, 88),
}

class MelodyPostProcessor:
    def assess_quality(self, notes: List[MelodyNote], duration_seconds: float, mode: MelodyMode, source_separated: bool = False) -> tuple[float, list[str]]:
        """Estimate transcription reliability without claiming source isolation."""
        warnings = [] if source_separated else [
            "Melody is estimated from the original full mix without source separation; it may follow accompaniment rather than the lead."
        ]
        if not notes:
            return 0.0, warnings

        minutes = max(duration_seconds / 60.0, 1 / 60)
        notes_per_minute = len(notes) / minutes
        adjacent = list(zip(notes, notes[1:]))
        large_jump_ratio = (
            sum(abs(right.midi - left.midi) > 12 for left, right in adjacent) / len(adjacent)
            if adjacent else 0.0
        )
        density_score = 1.0
        if notes_per_minute < 8:
            density_score = 0.3
            warnings.append("The estimated melody is sparse; some lead notes may be missing.")
        elif notes_per_minute > 180:
            density_score = 0.4
            warnings.append("The estimated melody is unusually dense and may include accompaniment notes.")

        continuity_score = max(0.2, 1.0 - large_jump_ratio * 2.0)
        mode_ceiling = 0.58 if mode == MelodyMode.MIX else 0.68
        confidence = min(mode_ceiling, 0.10 + 0.25 * density_score + 0.30 * continuity_score)
        if confidence < 0.5:
            warnings.append("Melody reliability is low; verify it by ear before using the score or Tab.")
        return round(confidence, 2), warnings

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
            ordered_pitches = sorted(note.midi for note in playable)
            if mode == MelodyMode.VOCAL:
                # Lead vocals commonly sit above the accompaniment, while the
                # very highest candidate is often an overtone or cymbal leak.
                center_index = min(ceil((len(ordered_pitches) - 1) * 0.7), max(0, len(ordered_pitches) - 2))
                center = float(ordered_pitches[center_index])
            elif mode == MelodyMode.GUITAR:
                center_index = min(round((len(ordered_pitches) - 1) * 0.6), max(0, len(ordered_pitches) - 2))
                center = float(ordered_pitches[center_index])
            else:
                center = float(median_low(ordered_pitches))
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
