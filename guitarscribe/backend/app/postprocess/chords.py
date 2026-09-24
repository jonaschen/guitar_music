from typing import List
import re
from ..models.analysis import ChordEvent, BeatAnalysis, ChordComplexity
from .harmony import apply_harmonic_context

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
                match = re.match(r'^([A-G][b#]?(?:maj7|m7|dim|aug|7|m)?(?:/[A-G][b#]?)?)', chord.symbol)
                if match:
                    chord.symbol = match.group(1)
        return chords

    def mark_review_candidates(self, chords: List[ChordEvent]) -> List[ChordEvent]:
        """Flag uncertainty without silently replacing musically valid outliers."""
        for index, chord in enumerate(chords):
            if chord.edited:
                chord.needs_review = False
                chord.review_reasons = []
                continue
            reasons: list[str] = []
            if chord.confidence < 0.5:
                reasons.append("low_confidence")
            if chord.end - chord.start < 0.3:
                reasons.append("short_event")
            if chord.detected_symbol and chord.detected_symbol != chord.symbol:
                reasons.append("theory_corrected")
            if chord.harmonic_function == "chromatic" and chord.confidence < 0.65:
                reasons.append("low_confidence_chromatic")
            if chord.harmonic_function == "modal_mixture" and chord.confidence < 0.65:
                reasons.append("low_confidence_modal_mixture")
            if 0 < index < len(chords) - 1:
                previous, following = chords[index - 1], chords[index + 1]
                if previous.symbol == following.symbol != chord.symbol:
                    reasons.append("isolated_outlier")
            chord.review_reasons = list(dict.fromkeys(reasons))
            chord.needs_review = bool(chord.review_reasons)
        return chords

    def process(
        self, chords: List[ChordEvent], beats: BeatAnalysis, complexity: ChordComplexity,
        key: str = "C", mode: str = "major",
    ) -> List[ChordEvent]:
        # Segmentation and sequence selection belong to the analyzer. Repeating
        # smoothing here erased short changes and N.C. gaps, while independent
        # endpoint snapping could collapse a valid short interval to zero.
        # Keep candidate evidence and intervals intact for review and replay.
        chords = [chord.model_copy(deep=True) for chord in chords]
        chords = self.simplify(chords, complexity)
        chords = apply_harmonic_context(chords, key, mode, correction_threshold=0.0)
        chords = self.mark_review_candidates(chords)
        return chords
