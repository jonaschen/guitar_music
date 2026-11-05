"""Read SWD's recording-relative annotations without inventing beat positions."""

import csv
import hashlib
import math
from pathlib import Path
import re

import mir_eval

from .annotations import QualityAnnotation
from .quality_report import _chord_timeline


_BASS_NOTE = re.compile(r"[A-G][#b]*\Z")
_INTERVALS = ("1", "b2", "2", "b3", "3", "4", "b5", "5", "b6", "6", "b7", "7")


def swd_chord_label(label: str) -> str:
    """Convert a spelled bass pitch to Harte's relative interval, retaining quality."""
    label = label.strip()
    if "/" in label:
        chord, bass = label.rsplit("/", 1)
        if _BASS_NOTE.fullmatch(bass):
            root = chord.split(":", 1)[0]
            interval = (mir_eval.chord.pitch_class_to_semitone(bass)
                        - mir_eval.chord.pitch_class_to_semitone(root)) % 12
            label = f"{chord}/{_INTERVALS[interval]}"
    # Validate semantics as well as grammar before spending time on inference.
    mir_eval.chord.encode(label)
    return label


def build_swd_annotation(chords_path: Path, measures_path: Path, source_file: Path,
                         recording_id: str, *, rights_note: str, meter: str,
                         clip_end: float = 45.0) -> QualityAnnotation:
    if not math.isfinite(clip_end) or clip_end <= 0:
        raise ValueError("clip_end must be finite and positive")
    with chords_path.open(encoding="utf-8-sig", newline="") as handle:
        chords = [{"start": float(row["start"]), "end": float(row["end"]),
                   "label": swd_chord_label(row["shorthand"])}
                  for row in csv.DictReader(handle, delimiter=";")]
    if not chords or any(not math.isfinite(c[k]) for c in chords for k in ("start", "end")):
        raise ValueError("SWD chords must have finite, nonempty annotations")
    if any(right["start"] < left["start"] for left, right in zip(chords, chords[1:])):
        raise ValueError("SWD chord annotations must be ordered")
    with measures_path.open(encoding="utf-8-sig", newline="") as handle:
        measures = [(float(row["start"]), float(row["measure"]))
                    for row in csv.DictReader(handle, delimiter=";")]
    if any(not math.isfinite(t) or not math.isfinite(m) or t < 0 or m < 1 for t, m in measures):
        raise ValueError("Invalid SWD measure annotation")
    if any(t2 <= t1 or m2 <= m1 for (t1, m1), (t2, m2) in zip(measures, measures[1:])):
        raise ValueError("SWD measure positions must increase")
    # The dataset's final fractional measure marks the end, not another downbeat.
    downbeats = [{"time": t} for t, measure in measures if measure.is_integer()]
    annotation = QualityAnnotation(
        recording_id=recording_id, source_file=str(source_file),
        source_sha256=hashlib.sha256(source_file.read_bytes()).hexdigest(),
        rights_note=rights_note,
        difficulty="hard", excerpt_start=max(0.0, chords[0]["start"]),
        excerpt_end=min(clip_end, chords[-1]["end"]), meter=meter,
        downbeats=downbeats, chords=chords,
        listening_notes=["Published vocal+piano reference; not pop acceptance. No beat/BPM interpolation."],
    )
    _chord_timeline(annotation.chords, annotation.excerpt_start, annotation.excerpt_end, reference=True)
    return annotation
