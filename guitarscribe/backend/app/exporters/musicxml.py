from xml.etree.ElementTree import Element, SubElement, tostring

from ..models.score import SongScore


def export_musicxml(score: SongScore) -> str:
    root = Element("score-partwise", version="3.1")
    part_list = SubElement(root, "part-list")
    score_part = SubElement(part_list, "score-part", id="P1")
    SubElement(score_part, "part-name").text = "GuitarScribe Melody"
    part = SubElement(root, "part", id="P1")
    measure = SubElement(part, "measure", number="1")
    attributes = SubElement(measure, "attributes")
    SubElement(attributes, "divisions").text = "480"
    for note in score.melody:
        node = SubElement(measure, "note")
        pitch = SubElement(node, "pitch")
        names = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
        alters = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]
        SubElement(pitch, "step").text = names[note.midi % 12]
        if alters[note.midi % 12]:
            SubElement(pitch, "alter").text = "1"
        SubElement(pitch, "octave").text = str(note.midi // 12 - 1)
        SubElement(node, "duration").text = str(max(1, round((note.end - note.start) * score.analysis.bpm / 60 * 480)))
        SubElement(node, "type").text = "quarter"
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="unicode")
