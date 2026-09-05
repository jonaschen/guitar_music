from app.models.analysis import ChordEvent
from app.models.score import SongScore
from app.services.voicing_optimizer import SongVoicingOptimizer


def test_optimizer_assigns_available_voicings():
    score = SongScore(chords=[ChordEvent(id="g", start=0, end=1, symbol="G"), ChordEvent(id="c", start=1, end=2, symbol="C")])
    optimized = SongVoicingOptimizer().optimize(score)
    assert [chord.voicing_id for chord in optimized.chords] == ["open-g", "open-c"]
    assert all(chord.available_voicings for chord in optimized.chords)
