"""Safe scaffolding for human-authored quality annotations."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .annotations import QualityAnnotation


def create_annotation_draft(
    source_audio: Path,
    output_file: Path,
    recording_id: str,
    rights_note: str,
    difficulty: str,
    excerpt_start: float,
    excerpt_end: float,
    tempo_bpm: float | None = None,
    meter: str = "4/4",
) -> Path:
    """Create metadata only; musical ground truth remains explicitly empty."""
    if output_file.exists():
        raise FileExistsError(f"Annotation draft already exists: {output_file}")
    digest = hashlib.sha256(source_audio.read_bytes()).hexdigest()
    annotation = QualityAnnotation(
        recording_id=recording_id,
        evaluation_tier="quality_gate",
        annotation_status="draft",
        source_file=source_audio.name,
        source_sha256=digest,
        rights_note=rights_note,
        difficulty=difficulty,
        excerpt_start=excerpt_start,
        excerpt_end=excerpt_end,
        tempo_bpm=tempo_bpm,
        meter=meter,
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(annotation.model_dump_json(indent=2) + "\n")
    return output_file
