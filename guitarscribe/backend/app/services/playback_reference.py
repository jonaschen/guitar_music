"""Deterministic listening control; no input audio or musical inference."""
from ..models.analysis import BeatInfo, ChordEvent, RhythmSuggestion
from ..models.score import SongScore, SongInfo, AnalysisSummary


def reference_score(within_bar: bool = False) -> SongScore:
    symbols = ["C", "Am", "F", "G", "Am", "F", "G", "C"] if within_bar else ["C", "Am", "F", "G"]
    span = 1.25 if within_bar else 2.5
    return SongScore(
        song=SongInfo(title="Four-bar playback control", duration_seconds=10),
        analysis=AnalysisSummary(bpm=96, time_signature="4/4", key="C"),
        beats=[BeatInfo(time=index * 0.625, beat=index % 4 + 1, measure=index // 4 + 1)
               for index in range(16)],
        chords=[ChordEvent(id=f"reference-{index}", start=index * span, end=(index + 1) * span, symbol=symbol)
                for index, symbol in enumerate(symbols)],
        rhythm=RhythmSuggestion(
            subdivision=8, pattern_id="reference-straight-4-4", label="Straight 4/4 control",
            display=["D", None, "D", "U", None, "U", "D", "U"],
            accents=[1, 0, 0.65, 0.4, 0, 0.4, 0.75, 0.4],
        ),
    )
