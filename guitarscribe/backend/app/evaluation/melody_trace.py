"""Expose legacy note-selection stages for diagnostics, not production tuning."""

from ..models.analysis import BeatInfo, MelodyMode, MelodyNote
from ..postprocess.melody import MelodyPostProcessor
from .melody_structure import inspect_melody_structure


def trace_melody_postprocess(notes: list[MelodyNote], beats: list[BeatInfo], mode: MelodyMode,
                             start: float, end: float) -> dict:
    processor = MelodyPostProcessor()
    current = [note.model_copy(deep=True) for note in notes]
    originals = {note.id: note for note in notes}
    stages = {}

    def record(name):
        stages[name] = {
            "notes": [note.model_dump(mode="json") for note in current],
            "structure": inspect_melody_structure(current, start, end),
            "timing_changes_from_raw": [
                {"id": note.id,
                 "start_shift_seconds": note.start - originals[note.id].start,
                 "end_shift_seconds": note.end - originals[note.id].end,
                 "duration_ratio": (note.end - note.start) / (originals[note.id].end - originals[note.id].start)}
                for note in current if note.id in originals
                and originals[note.id].end > originals[note.id].start
                and (abs(note.start - originals[note.id].start) > 1e-9
                     or abs(note.end - originals[note.id].end) > 1e-9)
            ],
        }

    record("raw_candidates")
    operations = [
        ("duration_filter", processor.remove_short_notes),
        ("confidence_filter", processor.remove_low_confidence),
        ("beat_quantization", lambda ns: processor.quantize_to_beats(ns, beats) if beats else ns),
        ("onset_bucket_selection", lambda ns: processor.select_monophonic_line(ns, mode)),
        ("register_filter", processor.remove_register_outliers),
        ("same_pitch_merge", processor.merge_repeated),
    ]
    for name, operation in operations:
        current = operation([note.model_copy(deep=True) for note in current])
        record(name)
    return {"status": "diagnostic_only", "stages": stages}
