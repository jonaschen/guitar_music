from app.models.analysis import ChordEvent, ChordVoicing
from app.models.score import SongScore
from app.services.voicing_optimizer import SongVoicingOptimizer


def test_optimizer_assigns_available_voicings():
    score = SongScore(chords=[ChordEvent(id="g", start=0, end=1, symbol="G"), ChordEvent(id="c", start=1, end=2, symbol="C")])
    optimized = SongVoicingOptimizer().optimize(score)
    assert [chord.voicing_id for chord in optimized.chords] == ["open-g", "open-c"]
    assert all(chord.available_voicings for chord in optimized.chords)


def test_optimizer_prefers_common_tones_and_small_finger_motion():
    class StubProvider:
        def get(self, symbol, capo=0):
            return {
                "G": [ChordVoicing(id="g", symbol="G", shape_symbol="G", frets=[3, 2, 0, 0, 0, 3], base_fret=1, difficulty=1)],
                "C": [
                    ChordVoicing(id="rough", symbol="C", shape_symbol="C", frets=[1, 1, 3, 3, 3, 1], base_fret=1, difficulty=1),
                    ChordVoicing(id="smooth", symbol="C", shape_symbol="C", frets=[None, 3, 2, 0, 1, 0], base_fret=1, difficulty=1),
                ],
            }[symbol]

    score = SongScore(chords=[ChordEvent(id="g", start=0, end=1, symbol="G"), ChordEvent(id="c", start=1, end=2, symbol="C")])

    optimized = SongVoicingOptimizer(StubProvider()).optimize(score)

    assert [chord.voicing_id for chord in optimized.chords] == ["g", "smooth"]


def test_optimizer_uses_whole_progression_instead_of_greedy_choice():
    easy = ChordVoicing(id="easy", symbol="C", shape_symbol="C", frets=[None, 3, 2, 0, 1, 0], base_fret=1, difficulty=0.9)
    connected = ChordVoicing(id="connected", symbol="C", shape_symbol="C", frets=[8, 10, 10, 9, 8, 8], base_fret=8, difficulty=1.0)
    high_g = ChordVoicing(id="high-g", symbol="G", shape_symbol="G", frets=[10, 10, 9, 7, 8, 7], base_fret=7, difficulty=1.0)

    selected = SongVoicingOptimizer._optimize_segment([[easy, connected], [high_g]])

    assert [voicing.id for voicing in selected] == ["connected", "high-g"]
