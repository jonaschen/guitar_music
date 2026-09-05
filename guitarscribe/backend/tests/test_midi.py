from app.exporters.midi import export_midi
from app.models.analysis import MelodyNote
from app.models.score import AnalysisSummary, SongScore


def test_midi_export_has_standard_header_and_note_events():
    score = SongScore(
        analysis=AnalysisSummary(bpm=120),
        melody=[MelodyNote(id="n1", start=0, end=0.5, midi=60, note="C4")],
    )

    output = export_midi(score)

    assert output.startswith(b"MThd\x00\x00\x00\x06")
    assert b"MTrk" in output
    assert bytes([0x90, 60, 96]) in output
    assert bytes([0x80, 60, 0]) in output
