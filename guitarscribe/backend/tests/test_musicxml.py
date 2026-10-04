from app.exporters.musicxml import export_musicxml
from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.models.score import SongScore
from xml.etree import ElementTree
import pytest


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


@pytest.mark.parametrize("meter,count,capacity", [("4/4", 4, 1920), ("6/8", 6, 1440)])
def test_local_grid_controls_notated_lengths_and_tempo_without_moving_source(meter, count, capacity):
    # Nonuniform pulses: first pulse .6 s, next .4 s, remaining .5 s.
    times = [0, .6, 1] + [1 + i * .5 for i in range(1, count - 2)]
    end = times[-1] + .5
    score = SongScore(song={"duration_seconds": end + 2},
        analysis={"bpm": 120, "time_signature": meter},
        beats=[BeatInfo(time=t, beat=i + 1, measure=1) for i, t in enumerate(times)] + [BeatInfo(time=end, beat=1, measure=2)],
        melody=[MelodyNote(id="n", start=.6, end=1, midi=60, note="C4")])
    before = score.model_dump_json()
    measure = ElementTree.fromstring(export_musicxml(score)).find(".//measure")
    assert sum(int(n.findtext("duration")) for n in measure.findall("note")) == capacity
    assert int(measure.findtext("note[pitch]/duration")) == capacity // count
    sounds = measure.findall("sound")
    assert [int(s.findtext("offset")) for s in sounds] == [i * capacity // count for i in range(count)]
    # Reconstruct seconds independently from serialized tempo offsets.
    reconstructed = [0.0]
    for sound in sounds:
        reconstructed.append(reconstructed[-1] + (capacity / count / 480) * 60 / float(sound.attrib["tempo"]))
    assert reconstructed == pytest.approx(times + [end], abs=1e-8)
    assert score.model_dump_json() == before


def test_calibrated_boundary_splits_tied_note_using_local_notated_duration():
    score = SongScore(song={"duration_seconds": 4}, analysis={"bpm": 120},
        beats=[BeatInfo(time=0, beat=1, measure=1), BeatInfo(time=2.4, beat=1, measure=2), BeatInfo(time=4, beat=1, measure=3)],
        melody=[MelodyNote(id="n", start=2.1, end=2.8, midi=60, note="C4")])
    root = ElementTree.fromstring(export_musicxml(score))
    notes = root.findall(".//note[pitch]")
    assert [int(n.findtext("duration")) for n in notes] == [240, 480]
    assert [[t.attrib["type"] for t in n.findall("tie")] for n in notes] == [["start"], ["stop"]]
    for measure in root.findall(".//measure"):
        assert sum(int(n.findtext("duration")) for n in measure.findall("note")) == 1920


def test_fractional_note_boundaries_do_not_accumulate_measure_rounding_error():
    score = SongScore(song={"duration_seconds": 2.3},
        beats=[BeatInfo(time=0, beat=1, measure=1), BeatInfo(time=2.3, beat=1, measure=2)],
        melody=[MelodyNote(id=str(i), start=.013 + i * .07, end=.044 + i * .07, midi=60, note="C4") for i in range(30)])
    measure = ElementTree.fromstring(export_musicxml(score)).find(".//measure")
    assert len(measure.findall("note[pitch]")) == 30
    assert sum(int(n.findtext("duration")) for n in measure.findall("note")) == 1920
