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


def test_template_accents_survive_selection_and_listing(tmp_path):
    (tmp_path / "steady.json").write_text('{"id":"steady","time_signature":"4/4","subdivision":4,"events":["D","D","D","D"],"accents":[1,0.5,0.8,0.5]}')
    suggester = RhythmSuggester(tmp_path)
    assert suggester.available_patterns("4/4")[0].accents == [1, 0.5, 0.8, 0.5]
    assert suggester.suggest(make_beats(), ChordAnalysis()).accents == [1, 0.5, 0.8, 0.5]


def test_duplicate_analysis_regions_do_not_change_rhythm_selection(tmp_path):
    (tmp_path / "quarter.json").write_text('{"id":"quarter","time_signature":"4/4","subdivision":4,"events":["D","D","D","D"]}')
    (tmp_path / "flowing.json").write_text('{"id":"flowing","time_signature":"4/4","subdivision":8,"events":["D",null,"D","U",null,"U","D","U"]}')
    suggester = RhythmSuggester(tmp_path)
    merged = ChordAnalysis(chords=[ChordEvent(id="c", start=0, end=4, symbol="C")])
    regions = ChordAnalysis(chords=[ChordEvent(id=str(i), start=i * 0.5, end=(i + 1) * 0.5, symbol="C") for i in range(8)])
    assert suggester.suggest(make_beats(), regions).pattern_id == suggester.suggest(make_beats(), merged).pattern_id == "flowing"


def test_duration_specific_template_is_manual_only(tmp_path):
    (tmp_path / "manual.json").write_text('{"id":"manual","time_signature":"4/4","subdivision":4,"events":["D","D","D","D"],"auto_suggest":false}')
    suggester = RhythmSuggester(tmp_path)
    assert suggester.available_patterns("4/4")[0].pattern_id == "manual"
    assert suggester.suggest(make_beats(), ChordAnalysis()).pattern_id == "basic_8th"
