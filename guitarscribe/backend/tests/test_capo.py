from app.models.analysis import ChordEvent
from app.models.score import SongScore
from app.services.capo import CapoAdvisor
from app.models.analysis import ChordVoicing
import pytest


def test_capo_advisor_ranks_covered_open_shapes():
    score = SongScore(chords=[ChordEvent(id="1", start=0, end=1, symbol="G"), ChordEvent(id="2", start=1, end=2, symbol="C")])
    recommendations = CapoAdvisor().recommend(score, max_capo=2)
    assert recommendations[0].capo == 0
    assert recommendations[0].covered_chords == 2


def test_capo_does_not_count_root_only_fallback_as_a_complete_chord():
    score = SongScore(chords=[ChordEvent(id='x', start=0, end=2, symbol='Cmaj9')])
    before = score.model_dump()
    result = CapoAdvisor().recommend(score, max_capo=2)
    assert all(row.covered_chords == 0 and row.total_chords == 1 for row in result)
    assert score.model_dump() == before


def test_capo_respects_fret_and_capo_limits_and_skips_silence():
    score = SongScore(chords=[ChordEvent(id='x', start=0, end=1, symbol='G'), ChordEvent(id='rest', start=1, end=2, symbol='N.C.')])
    score.guitar.max_fret = 2; score.guitar.max_capo = 1
    result = CapoAdvisor().recommend(score, max_capo=8)
    assert {r.capo for r in result} == {0, 1}
    assert all(r.total_chords == 1 for r in result)
    assert next(r for r in result if r.capo == 0).covered_chords == 0


def test_empty_song_and_nonstandard_tuning_do_not_invent_recommendations():
    assert CapoAdvisor().recommend(SongScore()) == []
    score = SongScore(chords=[ChordEvent(id='x', start=0, end=1, symbol='C')])
    score.guitar.tuning[0] = 38
    with pytest.raises(ValueError, match='標準調弦'): CapoAdvisor().recommend(score)


def shape(name, fret, difficulty=1):
    return ChordVoicing(id=name, symbol='C', shape_symbol='C', frets=[fret,fret+2,fret+2,fret+1,fret,fret],base_fret=fret,difficulty=difficulty)


def test_capo_ranking_uses_progression_cost_not_only_individual_ease():
    class Provider:
        def get(self, symbol, capo=0, max_fret=15):
            if capo == 1: return [shape('smooth', 4, 1.1)]
            return [shape('low' if symbol == 'C' else 'high', 1 if symbol == 'C' else 12)]
    advisor = CapoAdvisor(); advisor.voicings = Provider()
    score = SongScore(chords=[ChordEvent(id='c', start=0, end=1, symbol='C'), ChordEvent(id='g', start=1, end=2, symbol='G')])
    result = advisor.recommend(score, max_capo=1)
    assert result[0].capo == 1
    assert result[0].transition_cost < result[1].transition_cost
    assert result[0].ranking_score < result[1].ranking_score


def test_preferred_fret_is_a_soft_choice_and_silence_breaks_transition_cost():
    class Provider:
        def get(self, symbol, capo=0, max_fret=15): return [shape('low', 1)] if symbol == 'C' else [shape('high', 10)]
    advisor = CapoAdvisor(); advisor.voicings = Provider()
    score = SongScore(chords=[ChordEvent(id='c', start=0, end=1, symbol='C'),ChordEvent(id='r', start=1, end=2, symbol='N.C.'),ChordEvent(id='g', start=2,end=3,symbol='G')])
    result = advisor.recommend(score, max_capo=0, preferred_fret=10)[0]
    assert result.transition_cost == 0
    assert result.position_penalty > 0 and result.covered_chords == 2
    with pytest.raises(ValueError): advisor.recommend(score, preferred_fret=16)


def test_supported_slash_bass_is_retained_and_unsupported_slash_is_uncovered():
    score = SongScore(chords=[ChordEvent(id='a',start=0,end=1,symbol='C/E'),ChordEvent(id='b',start=1,end=2,symbol='Cmaj9/E')])
    result = CapoAdvisor().recommend(score,max_capo=0)[0]
    assert result.covered_chords == 1 and result.total_chords == 2


def test_preferred_position_selects_a_different_path_without_mutating_voicings():
    low, high = shape('low',1), shape('high',10)
    class Provider:
        def get(self, symbol, capo=0, max_fret=15): return [low,high]
    advisor = CapoAdvisor(); advisor.voicings = Provider()
    score = SongScore(chords=[ChordEvent(id='c',start=0,end=1,symbol='C')])
    result = advisor.recommend(score,max_capo=0,preferred_fret=10)[0]
    assert result.position_penalty == 0 and result.voicing_plan == {'c':'high'}
    assert low.difficulty == high.difficulty == 1
