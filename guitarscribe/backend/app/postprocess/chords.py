from typing import List
import re
from ..models.analysis import ChordEvent, BeatAnalysis, ChordComplexity

class ChordPostProcessor:
    def smooth_chords(self, chords: List[ChordEvent], beats: BeatAnalysis, min_duration: float = 0.3) -> List[ChordEvent]:
        result = []
        for chord in chords:
            dur = chord.end - chord.start
            if dur >= min_duration:
                result.append(chord)
            elif result:
                result[-1].end = chord.end
        return result

    def snap_to_beats(self, chords: List[ChordEvent], beats: BeatAnalysis, tolerance: float = 0.15) -> List[ChordEvent]:
        if not beats.beats:
            return chords
            
        beat_times = [b.time for b in beats.beats]
        
        for chord in chords:
            start_diffs = [abs(chord.start - bt) for bt in beat_times]
            end_diffs = [abs(chord.end - bt) for bt in beat_times]
            
            best_start = min(range(len(start_diffs)), key=start_diffs.__getitem__)
            if start_diffs[best_start] <= tolerance:
                chord.start = beat_times[best_start]
                
            best_end = min(range(len(end_diffs)), key=end_diffs.__getitem__)
            if end_diffs[best_end] <= tolerance:
                chord.end = beat_times[best_end]
                
        return chords

    def merge_consecutive(self, chords: List[ChordEvent]) -> List[ChordEvent]:
        if not chords:
            return []
            
        merged = [chords[0]]
        for chord in chords[1:]:
            if chord.symbol == merged[-1].symbol:
                merged[-1].end = max(merged[-1].end, chord.end)
            else:
                if chord.start < merged[-1].end:
                    chord.start = merged[-1].end
                if chord.end > chord.start:
                    merged.append(chord)
        return merged

    def smooth_low_confidence_return_chords(self, chords: List[ChordEvent], beats: BeatAnalysis) -> List[ChordEvent]:
        """Collapse a weak one-beat A-B-A flicker into a lead-sheet A span."""
        if len(chords) < 3 or len(beats.beats) < 2:
            return chords
        intervals = [right.time - left.time for left, right in zip(beats.beats, beats.beats[1:]) if right.time > left.time]
        typical_beat = sorted(intervals)[len(intervals) // 2] if intervals else 0.5
        result: list[ChordEvent] = []
        index = 0
        while index < len(chords):
            if index + 2 < len(chords):
                left, middle, right = chords[index:index + 3]
                middle_duration = middle.end - middle.start
                if (
                    left.symbol == right.symbol
                    and middle.confidence < 0.6
                    and middle_duration <= typical_beat * 1.25
                    and abs(left.end - middle.start) < 0.02
                    and abs(middle.end - right.start) < 0.02
                ):
                    left.end = right.end
                    left.confidence = max(left.confidence, right.confidence)
                    result.append(left)
                    index += 3
                    continue
            result.append(chords[index])
            index += 1
        return result

    def simplify(self, chords: List[ChordEvent], level: ChordComplexity) -> List[ChordEvent]:
        if level == ChordComplexity.FULL:
            return chords
            
        for chord in chords:
            if level == ChordComplexity.SIMPLE:
                # Match root + optional 'm' for minor, but NOT 'maj'
                match = re.match(r'^([A-G][b#]?)(m(?!aj))?', chord.symbol)
                if match:
                    chord.symbol = match.group(1) + (match.group(2) or '')
            elif level == ChordComplexity.STANDARD:
                match = re.match(r'^([A-G][b#]?(?:m)?(?:7|maj7|m7|dim|aug)?(?:/[A-G][b#]?)?)', chord.symbol)
                if match:
                    chord.symbol = match.group(1)
        return chords

    def process(self, chords: List[ChordEvent], beats: BeatAnalysis, complexity: ChordComplexity) -> List[ChordEvent]:
        chords = self.smooth_chords(chords, beats)
        chords = self.snap_to_beats(chords, beats)
        chords = self.merge_consecutive(chords)
        chords = self.smooth_low_confidence_return_chords(chords, beats)
        chords = self.simplify(chords, complexity)
        return chords
