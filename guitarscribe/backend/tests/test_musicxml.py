from app.exporters.musicxml import export_musicxml
from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.models.score import SongScore
from xml.etree import ElementTree


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


def test_edited_long_note_keeps_duration_across_bars_with_sound_and_notation_ties():
    score = SongScore(song={"duration_seconds": 6}, melody=[
        MelodyNote(id="manual", start=1.5, end=4.5, midi=64, note="E4", string=1, fret=0, edited=True)
    ])
    root = ElementTree.fromstring(export_musicxml(score))
    notes = root.findall(".//note[pitch]")
    assert [int(n.findtext("duration")) for n in notes] == [480, 1920, 480]
    assert [[t.attrib["type"] for t in n.findall("tie")] for n in notes] == [["start"], ["stop", "start"], ["stop"]]
    assert [[t.attrib["type"] for t in n.findall("notations/tied")] for n in notes] == [["start"], ["stop", "start"], ["stop"]]
    assert all(n.findtext("notations/technical/fret") == "0" for n in notes)


def test_manual_pickup_before_first_detected_downbeat_is_not_lost():
    score = SongScore(song={"duration_seconds": 3}, beats=[BeatInfo(time=0.5, beat=1, measure=1)],
                      melody=[MelodyNote(id="pickup", start=0.1, end=0.4, midi=60, note="C4")])
    root = ElementTree.fromstring(export_musicxml(score))
    assert root.find(".//measure").attrib["number"] == "0"
    assert root.findtext(".//note[pitch]/pitch/step") == "C"
