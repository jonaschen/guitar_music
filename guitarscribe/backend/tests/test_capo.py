from app.models.analysis import ChordEvent
from app.models.score import SongScore
from app.services.capo import CapoAdvisor


def test_capo_advisor_ranks_covered_open_shapes():
    score = SongScore(chords=[ChordEvent(id="1", start=0, end=1, symbol="G"), ChordEvent(id="2", start=1, end=2, symbol="C")])
    recommendations = CapoAdvisor().recommend(score, max_capo=2)
    assert recommendations[0].capo == 0
    assert recommendations[0].covered_chords == 2
