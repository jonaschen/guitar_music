from app.models.analysis import BeatAnalysis, BeatInfo, ChordAnalysis, ChordEvent
from app.postprocess.rhythm import RhythmSuggester


def make_beats() -> BeatAnalysis:
    return BeatAnalysis(
        bpm=120,
        confidence=0.8,
        beats=[BeatInfo(time=index * 0.5, beat=index % 4 + 1, measure=index // 4 + 1) for index in range(8)],
    )


def test_rhythm_suggester_loads_templates_and_uses_harmonic_density(tmp_path):
    patterns = tmp_path / "patterns"
    patterns.mkdir()
    (patterns / "steady.json").write_text('{"id":"steady","name":"Steady","time_signature":"4/4","subdivision":4,"events":["D","D","D","D"]}')
    (patterns / "flowing.json").write_text('{"id":"flowing","name":"Flowing","time_signature":"4/4","subdivision":8,"events":["D",null,"D","U",null,"U","D","U"]}')
    suggester = RhythmSuggester(patterns)

    sparse = suggester.suggest(make_beats(), ChordAnalysis(chords=[ChordEvent(id="one", start=0, end=4, symbol="C")]))
    dense = suggester.suggest(make_beats(), ChordAnalysis(chords=[ChordEvent(id=str(index), start=index, end=index + 0.5, symbol="C") for index in range(4)]))

    assert sparse.pattern_id == "flowing"
    assert dense.pattern_id == "steady"


def test_rhythm_suggester_falls_back_when_templates_are_missing(tmp_path):
    suggestion = RhythmSuggester(tmp_path / "missing").suggest(make_beats(), ChordAnalysis())

    assert suggestion.pattern_id == "basic_8th"
    assert suggestion.display[0] == "D"
