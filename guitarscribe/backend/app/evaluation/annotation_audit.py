"""Integrity checks for human-authored quality annotations and source audio."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .annotations import QualityAnnotation


def _issue(recording_id: str, code: str, message: str, severity: str = "error") -> dict[str, str]:
    return {"recording_id": recording_id, "severity": severity, "code": code, "message": message}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_quality_annotations(annotations_directory: Path, audio_directory: Path) -> dict[str, Any]:
    annotation_paths = sorted(annotations_directory.glob("*.json"))
    issues: list[dict[str, str]] = []
    annotations: list[QualityAnnotation] = []
    for path in annotation_paths:
        try:
            annotations.append(QualityAnnotation.model_validate_json(path.read_text()))
        except ValueError as exc:
            issues.append(_issue(path.stem, "invalid_schema", str(exc)))

    recording_ids = [annotation.recording_id for annotation in annotations]
    for recording_id in sorted(set(recording_ids)):
        if recording_ids.count(recording_id) > 1:
            issues.append(_issue(recording_id, "duplicate_recording_id", "recording_id must be unique"))

    audio_root = audio_directory.resolve()
    for annotation in annotations:
        recording_id = annotation.recording_id
        if annotation.evaluation_tier == "quality_gate":
            if annotation.annotation_status != "reviewed":
                issues.append(_issue(recording_id, "unreviewed_annotation", "quality gate must be reviewed"))
            if not annotation.reviewed_by:
                issues.append(_issue(recording_id, "missing_reviewer", "quality gate requires reviewed_by"))
        if annotation.source_file:
            source_path = (audio_directory / annotation.source_file).resolve()
            if source_path != audio_root and audio_root not in source_path.parents:
                issues.append(_issue(recording_id, "unsafe_source_path", annotation.source_file))
            elif not source_path.is_file():
                issues.append(_issue(recording_id, "missing_source", annotation.source_file))
            elif _sha256(source_path) != annotation.source_sha256:
                issues.append(_issue(recording_id, "source_hash_mismatch", annotation.source_file))
        elif annotation.evaluation_tier == "quality_gate":
            issues.append(_issue(recording_id, "missing_source_file", "quality gate has no source_file"))

        beat_times = [point.time for point in annotation.beats]
        if beat_times != sorted(set(beat_times)):
            issues.append(_issue(recording_id, "invalid_beats", "beats must be unique and increasing"))
        if any(time < annotation.excerpt_start or time >= annotation.excerpt_end for time in beat_times):
            issues.append(_issue(recording_id, "beat_outside_excerpt", "beat lies outside excerpt"))
        if annotation.evaluation_tier == "quality_gate":
            if annotation.tempo_bpm is None:
                issues.append(_issue(recording_id, "missing_tempo", "quality gate requires tempo_bpm"))
            elif not beat_times:
                issues.append(_issue(recording_id, "missing_beats", "quality gate requires beat ground truth"))
            else:
                expected_interval = 60 / annotation.tempo_bpm
                if beat_times[0] - annotation.excerpt_start > expected_interval * 1.5:
                    issues.append(_issue(recording_id, "beat_coverage_start", "beats do not cover excerpt start"))
                if annotation.excerpt_end - beat_times[-1] > expected_interval * 1.5:
                    issues.append(_issue(recording_id, "beat_coverage_end", "beats do not cover excerpt end"))
            if not annotation.downbeats:
                issues.append(_issue(recording_id, "missing_downbeats", "quality gate requires downbeat ground truth"))
        for downbeat in annotation.downbeats:
            if not any(abs(downbeat.time - beat) <= 0.05 for beat in beat_times):
                issues.append(_issue(recording_id, "downbeat_without_beat", f"{downbeat.time:.3f}s"))

        chords = sorted(annotation.chords, key=lambda chord: chord.start)
        if not chords:
            issues.append(_issue(recording_id, "missing_chords", "no chord ground truth"))
        else:
            if abs(chords[0].start - annotation.excerpt_start) > 0.02:
                issues.append(_issue(recording_id, "chord_coverage_start", "chords do not start at excerpt boundary"))
            for left, right in zip(chords, chords[1:]):
                difference = right.start - left.end
                if difference > 0.02:
                    issues.append(_issue(recording_id, "chord_gap", f"gap of {difference:.3f}s"))
                elif difference < -0.02:
                    issues.append(_issue(recording_id, "chord_overlap", f"overlap of {-difference:.3f}s"))
            if abs(chords[-1].end - annotation.excerpt_end) > 0.02:
                issues.append(_issue(recording_id, "chord_coverage_end", "chords do not end at excerpt boundary"))

    quality_gate_count = sum(item.evaluation_tier == "quality_gate" for item in annotations)
    error_count = sum(issue["severity"] == "error" for issue in issues)
    return {
        "schema_version": "1.0",
        "annotation_count": len(annotations),
        "quality_gate_count": quality_gate_count,
        "g0_target_count": 12,
        "g0_remaining_count": max(0, 12 - quality_gate_count),
        "smoke_count": sum(item.evaluation_tier == "smoke" for item in annotations),
        "difficulty_counts": {
            difficulty: sum(item.difficulty == difficulty for item in annotations if item.evaluation_tier == "quality_gate")
            for difficulty in ("easy", "medium", "hard")
        },
        "valid": error_count == 0 and bool(annotations),
        "ready_for_calibration": error_count == 0 and quality_gate_count > 0,
        "g0_baseline_ready": error_count == 0 and quality_gate_count >= 12,
        "issues": issues,
    }
