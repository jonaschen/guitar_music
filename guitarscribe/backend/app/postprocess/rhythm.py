import json
from pathlib import Path
from ..models.analysis import BeatAnalysis, ChordAnalysis, AudioFeatures, RhythmSuggestion


class RhythmSuggester:
    def __init__(self, patterns_dir: Path = Path("/app/rhythm-patterns")):
        self.patterns_dir = patterns_dir

    def _beats_per_bar(self, time_signature: str) -> int:
        try:
            return max(1, int(time_signature.split("/", 1)[0]))
        except (AttributeError, ValueError):
            return 4

    def _load_patterns(self, time_signature: str) -> list[dict]:
        """Load only small, well-formed local pattern templates.

        Templates are intentionally data-only: no user supplied code or rhythm
        expression is evaluated while analyzing an upload.
        """
        patterns: list[dict] = []
        if not self.patterns_dir.is_dir():
            return patterns
        beats_per_bar = self._beats_per_bar(time_signature)
        for path in sorted(self.patterns_dir.glob("*.json")):
            try:
                candidate = json.loads(path.read_text(encoding="utf-8"))
                subdivision = int(candidate["subdivision"])
                display = candidate.get("display", candidate.get("events"))
                supported = candidate.get("time_signatures", [candidate.get("time_signature", "4/4")])
                expected_steps = beats_per_bar * subdivision // 4
                pattern_id = candidate.get("pattern_id") or candidate.get("id")
                if (
                    not isinstance(display, list)
                    or not isinstance(supported, list)
                    or not pattern_id
                    or time_signature not in supported
                    or subdivision <= 0
                    or len(display) != expected_steps
                    or any(stroke not in {"D", "U", None} for stroke in display)
                ):
                    continue
                patterns.append({
                    "pattern_id": str(pattern_id),
                    "label": str(candidate.get("label") or candidate.get("name") or pattern_id),
                    "subdivision": subdivision,
                    "display": display,
                    "confidence": float(candidate.get("confidence", 0.7)),
                })
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return patterns

    def _fallback(self) -> RhythmSuggestion:
        return RhythmSuggestion(
            subdivision=8,
            pattern_id="basic_8th",
            display=["D", None, "D", "U", None, "U", "D", "U"],
            confidence=0.5,
            label="Basic eighth-note strum",
        )

    def suggest(self, beats: BeatAnalysis, chords: ChordAnalysis, features: AudioFeatures | None = None) -> RhythmSuggestion:
        patterns = self._load_patterns(beats.time_signature)
        if not patterns:
            return self._fallback()

        measure_count = max((beat.measure for beat in beats.beats), default=1)
        changes_per_measure = len(chords.chords) / measure_count
        # Dense harmonic changes leave fewer safe places for a flowing pattern;
        # sparse harmony benefits from a fuller eighth-note accompaniment.
        target_strokes = 4 if changes_per_measure >= 1.5 else 6 if changes_per_measure <= 0.75 else 5
        selected = min(
            patterns,
            key=lambda pattern: abs(sum(stroke is not None for stroke in pattern["display"]) - target_strokes),
        )
        beat_confidence = beats.confidence or 0.0
        return RhythmSuggestion(
            subdivision=selected["subdivision"],
            pattern_id=selected["pattern_id"],
            display=selected["display"],
            confidence=round(min(1.0, selected["confidence"] * (0.5 + beat_confidence * 0.5)), 3),
            label=selected["label"],
        )
