from collections import defaultdict
from bisect import bisect_right
import re
from xml.etree.ElementTree import Element, SubElement, tostring

from ..models.analysis import ChordEvent, MelodyNote
from ..models.score import SongScore


DIVISIONS = 480
PITCH_NAMES = (("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
               ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0))
KEY_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7, "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7}
CHORD_SYMBOL = re.compile(r"^([A-G])([#b]?)([^/]*)(?:/([A-G])([#b]?))?$")
CHORD_KINDS = {"": "major", "maj": "major", "m": "minor", "min": "minor",
               "7": "dominant", "maj7": "major-seventh", "M7": "major-seventh",
               "m7": "minor-seventh", "dim": "diminished", "dim7": "diminished-seventh",
               "m7b5": "half-diminished", "aug": "augmented", "+": "augmented",
               "sus2": "suspended-second", "sus4": "suspended-fourth",
               "6": "major-sixth", "m6": "minor-sixth", "9": "dominant-ninth",
               "maj9": "major-ninth", "m9": "minor-ninth", "5": "power"}


def _harmony(measure: Element, symbol: str, offset: int) -> None:
    normalized = symbol.strip().replace("♯", "#").replace("♭", "b")
    match = CHORD_SYMBOL.fullmatch(normalized)
    suffix = match[3].lstrip(":") if match else None
    if not match or suffix not in CHORD_KINDS:
        # Preserve unsupported labels visibly instead of inventing major harmony.
        direction = SubElement(measure, "direction", placement="above")
        SubElement(SubElement(direction, "direction-type"), "words").text = symbol
        SubElement(direction, "offset").text = str(offset)
        return
    harmony = SubElement(measure, "harmony")
    root = SubElement(harmony, "root")
    SubElement(root, "root-step").text = match[1]
    if match[2]:
        SubElement(root, "root-alter").text = "1" if match[2] == "#" else "-1"
    # kind text is the suffix, not the complete symbol (which would repeat the root).
    SubElement(harmony, "kind", text=suffix).text = CHORD_KINDS[suffix]
    if match[4]:
        bass = SubElement(harmony, "bass")
        SubElement(bass, "bass-step").text = match[4]
        if match[5]:
            SubElement(bass, "bass-alter").text = "1" if match[5] == "#" else "-1"
    SubElement(harmony, "offset").text = str(offset)


def _measure_clock(score: SongScore, number: int, start: float, end: float,
                   beats: int, beat_type: int, bpm: float, pickup: bool):
    """Map absolute seconds onto local divisions without cumulative rounding."""
    capacity = round((end - start) * bpm / 60 * DIVISIONS) if pickup else round(beats * 4 / beat_type * DIVISIONS)
    anchors = [(start, 0)]
    if not pickup:
        for beat in sorted(score.beats, key=lambda b: b.time):
            units = round((beat.beat - 1) * 4 / beat_type * DIVISIONS)
            if (beat.measure == number and anchors[-1][0] < beat.time < end
                    and anchors[-1][1] < units < capacity):
                anchors.append((beat.time, units))
    anchors.append((end, capacity))
    times = [a[0] for a in anchors]

    def position(time: float) -> int:
        i = max(0, min(len(anchors) - 2, bisect_right(times, time) - 1))
        left, right = anchors[i], anchors[i + 1]
        return round(left[1] + (time - left[0]) / (right[0] - left[0]) * (right[1] - left[1]))

    return position, anchors


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


def _tab_note(measure: Element, note: MelodyNote, duration: int, *, tie_start: bool = False, tie_stop: bool = False) -> None:
    node = SubElement(measure, "note")
    _pitch(node, note.midi)
    SubElement(node, "duration").text = str(duration)
    ties = (["stop"] if tie_stop else []) + (["start"] if tie_start else [])
    for kind in ties:
        SubElement(node, "tie", type=kind)
    SubElement(node, "type").text = _type(duration)
    notations = SubElement(node, "notations") if ties or (note.string is not None and note.fret is not None) else None
    if note.string is not None and note.fret is not None:
        technical = SubElement(notations, "technical")
        SubElement(technical, "string").text = str(note.string)
        SubElement(technical, "fret").text = str(note.fret)
    for kind in ties:
        SubElement(notations, "tied", type=kind)


def export_musicxml(score: SongScore) -> str:
    """Export a measure-aware guitar TAB score, including string and fret."""
    bpm = score.analysis.bpm if score.analysis.bpm > 0 else 120.0
    try:
        beats, beat_type = score.analysis.time_signature.split("/", maxsplit=1)
        beats, beat_type = int(beats), int(beat_type)
        if beats <= 0 or beat_type <= 0:
            raise ValueError("Invalid meter")
    except (AttributeError, ValueError):
        beats, beat_type = 4, 4
    measure_seconds = 60 / bpm * beats * 4 / beat_type
    starts = {beat.measure: beat.time for beat in score.beats if beat.beat == 1}
    measures = sorted(starts.items(), key=lambda item: item[1]) or [(1, 0.0)]
    if measures[0][1] > 0:
        measures.insert(0, (measures[0][0] - 1, 0.0))
    last_content = max([score.song.duration_seconds, *(note.end for note in score.melody), *(chord.end for chord in score.chords)], default=measure_seconds)
    while measures[-1][1] + measure_seconds < last_content:
        measures.append((measures[-1][0] + 1, measures[-1][1] + measure_seconds))
    notes_by_measure: dict[int, list[MelodyNote]] = defaultdict(list)
    chords_by_measure: dict[int, list[ChordEvent]] = defaultdict(list)
    for note in score.melody:
        for index, (_, start) in enumerate(measures):
            end = measures[index + 1][1] if index + 1 < len(measures) else start + measure_seconds
            if note.start < end and note.end > start:
                notes_by_measure[index].append(note)
    for chord in score.chords:
        index = max(index for index, (_, start) in enumerate(measures) if start <= chord.start)
        chords_by_measure[index].append(chord)
    root = Element("score-partwise", version="3.1")
    score_part = SubElement(SubElement(root, "part-list"), "score-part", id="P1")
    SubElement(score_part, "part-name").text = "GuitarScribe Melody Tab"
    part = SubElement(root, "part", id="P1")
    for index, (number, start) in enumerate(measures):
        end = measures[index + 1][1] if index + 1 < len(measures) else start + measure_seconds
        measure = SubElement(part, "measure", number=str(number))
        pickup = index == 0 and number not in starts and len(measures) > 1 and measures[1][0] in starts
        if pickup:
            measure.set("implicit", "yes")
        position, anchors = _measure_clock(score, number, start, end, beats, beat_type, bpm, pickup)
        if index == 0:
            attributes = SubElement(measure, "attributes")
            SubElement(attributes, "divisions").text = str(DIVISIONS)
            key = SubElement(attributes, "key")
            SubElement(key, "fifths").text = str(KEY_FIFTHS.get(score.key_context.target.key, 0))
            SubElement(key, "mode").text = score.key_context.target.mode
            time = SubElement(attributes, "time")
            SubElement(time, "beats").text, SubElement(time, "beat-type").text = str(beats), str(beat_type)
            clef = SubElement(attributes, "clef")
            SubElement(clef, "sign").text, SubElement(clef, "line").text = "TAB", "5"
            staff = SubElement(attributes, "staff-details")
            SubElement(staff, "staff-lines").text = "6"
            for string, midi in enumerate(reversed(score.guitar.tuning), start=1):
                tuning = SubElement(staff, "staff-tuning", line=str(string))
                step, alter = PITCH_NAMES[midi % 12]
                SubElement(tuning, "tuning-step").text = step
                if alter:
                    SubElement(tuning, "tuning-alter").text = str(alter)
                SubElement(tuning, "tuning-octave").text = str(midi // 12 - 1)
        # Explicit tempo offsets preserve source seconds when local pulse lengths vary.
        for left, right in zip(anchors, anchors[1:]):
            tempo = (right[1] - left[1]) / DIVISIONS * 60 / (right[0] - left[0])
            sound = SubElement(measure, "sound", tempo=f"{tempo:.9f}")
            SubElement(sound, "offset").text = str(left[1])
        for chord in sorted(chords_by_measure[index], key=lambda c: c.start):
            _harmony(measure, chord.symbol, position(chord.start))
        cursor = start
        for note in sorted(notes_by_measure[index], key=lambda item: item.start):
            note_start = max(cursor, note.start)
            if note_start > cursor:
                duration = position(note_start) - position(cursor)
                if duration > 0:
                    _rest(measure, duration)
            note_end = min(end, max(note.end, note_start))
            duration = position(note_end) - position(note_start)
            if duration > 0:
                _tab_note(measure, note, duration,
                          tie_start=note.end > end, tie_stop=note.start < start)
            cursor = max(cursor, note_end)
        if cursor < end:
            duration = position(end) - position(cursor)
            if duration > 0:
                _rest(measure, duration)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode")
