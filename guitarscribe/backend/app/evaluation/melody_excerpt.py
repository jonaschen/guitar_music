"""Create local, time-aligned listening diagnostics without changing a job."""

import json
from pathlib import Path

import soundfile as sf

from .melody_structure import inspect_melody_structure
from .sonification import render_note_sonification
from ..models.score import SongScore


def write_melody_excerpt(score: SongScore, source: Path, start: float, end: float, output: Path) -> dict:
    structure = inspect_melody_structure(score.melody, start, end)
    with sf.SoundFile(source) as audio:
        rate = audio.samplerate
        if end > len(audio) / rate or end > score.song.duration_seconds:
            raise ValueError("Excerpt exceeds recording or score duration")
        first, last = round(start * rate), round(end * rate)
        audio.seek(first)
        samples = audio.read(last - first, dtype="float32", always_2d=True)
    # Refuse to overwrite a previous audition or any persisted job directory.
    output.mkdir(parents=True, exist_ok=False)
    sf.write(output / "original.wav", samples, rate, subtype="PCM_16")
    render_note_sonification(score.melody, start, end, output / "estimated-melody.wav")
    report = {
        "status": "diagnostic_not_reference",
        "source_start_seconds": start,
        "source_end_seconds": end,
        "local_zero_equals_source_seconds": start,
        "structure": structure,
        "notes": [
            {"id": note.id, "midi": note.midi, "note": note.note,
             "source_start": note.start, "source_end": note.end,
             "local_start": max(start, note.start) - start,
             "local_end": min(end, note.end) - start}
            for note in score.melody if note.end > start and note.start < end
        ],
        "caveats": ["No pitch or timing correction applied", "Overlapping notes are retained",
                    "Synthetic tones are not isolated vocals", "Not a recognition accuracy score"],
    }
    (output / "diagnostic.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
