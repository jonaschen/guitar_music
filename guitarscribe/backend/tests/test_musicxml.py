from app.exporters.musicxml import export_musicxml
from app.models.analysis import MelodyNote
from app.models.score import SongScore


def test_musicxml_exports_detected_melody_note():
    score = SongScore(melody=[MelodyNote(id="n1", start=0, end=0.5, midi=60, note="C4")])

    output = export_musicxml(score)

    assert output.startswith('<?xml version="1.0"')
    assert '<score-partwise version="3.1">' in output
    assert "<step>C</step>" in output
    assert "<octave>4</octave>" in output
