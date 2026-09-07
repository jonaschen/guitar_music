from collections import defaultdict
from xml.etree.ElementTree import Element, SubElement, tostring

from ..models.analysis import MelodyNote
from ..models.score import SongScore


DIVISIONS = 480
PITCH_NAMES = (("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
               ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0))
KEY_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7, "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7}


def _units(seconds: float, bpm: float) -> int:
    return max(1, round(seconds * bpm / 60 * DIVISIONS))


def _type(duration: int) -> str:
    return "whole" if duration >= 1920 else "half" if duration >= 960 else "quarter" if duration >= 480 else "eighth" if duration >= 240 else "16th" if duration >= 120 else "32nd"


def _pitch(node: Element, midi: int) -> None:
    pitch = SubElement(node, "pitch")
    step, alter = PITCH_NAMES[midi % 12]
    SubElement(pitch, "step").text = step
    if alter:
        SubElement(pitch, "alter").text = str(alter)
    SubElement(pitch, "octave").text = str(midi // 12 - 1)


def _rest(measure: Element, duration: int) -> None:
    node = SubElement(measure, "note")
    SubElement(node, "rest")
    SubElement(node, "duration").text = str(duration)
    SubElement(node, "type").text = _type(duration)


def _tab_note(measure: Element, note: MelodyNote, duration: int) -> None:
    node = SubElement(measure, "note")
    _pitch(node, note.midi)
    SubElement(node, "duration").text = str(duration)
    SubElement(node, "type").text = _type(duration)
    if note.string is not None and note.fret is not None:
        technical = SubElement(SubElement(node, "notations"), "technical")
        SubElement(technical, "string").text = str(note.string)
        SubElement(technical, "fret").text = str(note.fret)


def export_musicxml(score: SongScore) -> str:
    """Export a measure-aware guitar TAB score, including string and fret."""
    bpm = score.analysis.bpm if score.analysis.bpm > 0 else 120.0
    try:
        beats, beat_type = score.analysis.time_signature.split("/", maxsplit=1)
        beats, beat_type = int(beats), int(beat_type)
    except (AttributeError, ValueError):
        beats, beat_type = 4, 4
    measure_seconds = 60 / bpm * beats * 4 / beat_type
    starts = {beat.measure: beat.time for beat in score.beats if beat.beat == 1}
    measures = sorted(starts.items(), key=lambda item: item[1]) or [(1, 0.0)]
    last_content = max([score.song.duration_seconds, *(note.end for note in score.melody), *(chord.end for chord in score.chords)], default=measure_seconds)
    while measures[-1][1] + measure_seconds < last_content:
        measures.append((measures[-1][0] + 1, measures[-1][1] + measure_seconds))
    notes_by_measure: dict[int, list[MelodyNote]] = defaultdict(list)
    chords_by_measure: dict[int, list[str]] = defaultdict(list)
    for note in score.melody:
        index = max(index for index, (_, start) in enumerate(measures) if start <= note.start)
        notes_by_measure[index].append(note)
    for chord in score.chords:
        index = max(index for index, (_, start) in enumerate(measures) if start <= chord.start)
        chords_by_measure[index].append(chord.symbol)
    root = Element("score-partwise", version="3.1")
    score_part = SubElement(SubElement(root, "part-list"), "score-part", id="P1")
    SubElement(score_part, "part-name").text = "GuitarScribe Melody Tab"
    part = SubElement(root, "part", id="P1")
    for index, (number, start) in enumerate(measures):
        end = measures[index + 1][1] if index + 1 < len(measures) else start + measure_seconds
        measure = SubElement(part, "measure", number=str(number))
        if index == 0:
            attributes = SubElement(measure, "attributes")
            SubElement(attributes, "divisions").text = str(DIVISIONS)
            key = SubElement(attributes, "key")
            SubElement(key, "fifths").text = str(KEY_FIFTHS.get(score.key_context.target.key, 0))
            SubElement(key, "mode").text = score.key_context.target.mode
            time = SubElement(attributes, "time")
            SubElement(time, "beats").text, SubElement(time, "beat-type").text = str(beats), str(beat_type)
            staff = SubElement(attributes, "staff-details")
            SubElement(staff, "staff-lines").text = "6"
            for string, midi in enumerate(reversed(score.guitar.tuning), start=1):
                tuning = SubElement(staff, "staff-tuning", line=str(string))
                step, alter = PITCH_NAMES[midi % 12]
                SubElement(tuning, "tuning-step").text = step
                if alter:
                    SubElement(tuning, "tuning-alter").text = str(alter)
                SubElement(tuning, "tuning-octave").text = str(midi // 12 - 1)
            clef = SubElement(attributes, "clef")
            SubElement(clef, "sign").text, SubElement(clef, "line").text = "TAB", "5"
        for symbol in dict.fromkeys(chords_by_measure[index]):
            harmony = SubElement(measure, "harmony")
            root_node = SubElement(harmony, "root")
            SubElement(root_node, "root-step").text = symbol[0].upper()
            kind = SubElement(harmony, "kind")
            kind.text, kind.attrib["text"] = ("minor" if len(symbol) > 1 and symbol[1] == "m" else "major"), symbol
        cursor = start
        for note in sorted(notes_by_measure[index], key=lambda item: item.start):
            note_start = max(cursor, note.start)
            if note_start > cursor:
                _rest(measure, _units(note_start - cursor, bpm))
            note_end = min(end, max(note.end, note_start))
            if note_end > note_start:
                _tab_note(measure, note, _units(note_end - note_start, bpm))
            cursor = max(cursor, note_end)
        if cursor < end:
            _rest(measure, _units(end - cursor, bpm))
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode")
