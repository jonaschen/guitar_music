from app.exporters.musicxml import export_musicxml
from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.models.score import SongScore


def test_musicxml_exports_detected_melody_note():
    score = SongScore(analysis={"bpm": 120, "time_signature": "4/4"}, beats=[BeatInfo(time=0, beat=1, measure=1), BeatInfo(time=2, beat=1, measure=2)], chords=[ChordEvent(id="c1", start=0, end=2, symbol="Am")], melody=[MelodyNote(id="n1", start=0.5, end=1, midi=69, note="A4", string=1, fret=5), MelodyNote(id="n2", start=2.25, end=2.75, midi=67, note="G4", string=1, fret=3)])

    output = export_musicxml(score)

    assert output.startswith('<?xml version="1.0"')
    assert '<score-partwise version="3.1">' in output
    assert "<step>A</step>" in output
    assert "<octave>4</octave>" in output
    assert "<sign>TAB</sign>" in output
    assert '<measure number="2">' in output
    assert "<rest />" in output
    assert "<root-step>A</root-step>" in output
    assert "<string>1</string><fret>5</fret>" in output
    assert "<string>1</string><fret>3</fret>" in output
