"""Deterministic listening control; no input audio or musical inference."""
from ..models.analysis import BeatInfo, ChordEvent, RhythmSuggestion
from ..models.score import SongScore, SongInfo, AnalysisSummary


def reference_score(within_bar: bool = False, groove: str = "balanced", chords_per_bar: int | None = None) -> SongScore:
    count = chords_per_bar or (2 if within_bar else 1)
    symbols = ["C", "Am", "F", "G", "Am", "F", "G", "C"] if count == 2 else ["C", "Am", "F", "G"]
    span = 1.25 if count == 2 else 2.5
    chords = [ChordEvent(id=f"reference-{index}", start=index * span, end=(index + 1) * span, symbol=symbol)
              for index, symbol in enumerate(symbols)]
    if count == 3:
        chords = [ChordEvent(id=f"reference-{bar}-{index}", start=bar * 2.5 + start, end=bar * 2.5 + end, symbol=symbol)
                  for bar, progression in enumerate([["C", "Am", "G"], ["F", "Dm", "G"], ["Am", "F", "G"], ["G", "F", "C"]])
                  for index, (symbol, start, end) in enumerate(zip(progression, [0, 1.25, 1.875], [1.25, 1.875, 2.5]))]
    display = ["D", None, "D", "U", "D", "U", "D", "U"]
    accents = [1, 0, 0.28, 0.18, 0.55, 0.18, 0.28, 0.18]
    if count == 3:
        display = ["D", None, "D", "U", "D", None, "D", None]
        accents = [1, 0, 0.28, 0.18, 0.55, 0, 0.28, 0]
    if groove == "syncopated":
        display = ["D", None, "D", "U", None, "U", "D", "U"]
        accents = [1, 0, 0.65, 0.4, 0, 0.4, 0.75, 0.4]
    return SongScore(
        song=SongInfo(title="Four-bar playback control", duration_seconds=10),
        analysis=AnalysisSummary(bpm=96, time_signature="4/4", key="C"),
        beats=[BeatInfo(time=index * 0.625, beat=index % 4 + 1, measure=index // 4 + 1)
               for index in range(16)],
        chords=chords,
        rhythm=RhythmSuggestion(
            subdivision=8, pattern_id=f"reference-{groove}-4-4", label="4/4 listening control",
            display=display,
            accents=accents,
        ),
    )
