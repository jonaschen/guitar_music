"""Immutable before/after quality bundles for analyzer regression review."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .annotations import QualityAnnotation
from .quality_report import evaluate_quality_layers
from .sonification import render_quality_sonifications
from ..models.score import SongScore


LAYERS = ("timing", "chord", "melody")


def _numeric_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, float]:
    return {
        key: float(after[key]) - float(before[key])
        for key in before.keys() & after.keys()
        if isinstance(before[key], (int, float)) and isinstance(after[key], (int, float))
    }


def _layer_summary(recordings: list[dict[str, Any]], layer: str) -> dict[str, dict[str, float]]:
    metric_names = sorted({
        metric
        for recording in recordings
        for metric, value in recording["baseline"][layer].items()
        if isinstance(value, (int, float)) and isinstance(recording["candidate"][layer].get(metric), (int, float))
    })
    summary: dict[str, dict[str, float]] = {}
    for metric in metric_names:
        baseline = [float(item["baseline"][layer][metric]) for item in recordings if metric in item["delta"][layer]]
        candidate = [float(item["candidate"][layer][metric]) for item in recordings if metric in item["delta"][layer]]
        if baseline:
            before_mean = sum(baseline) / len(baseline)
            after_mean = sum(candidate) / len(candidate)
            summary[metric] = {
                "baseline_mean": before_mean,
                "candidate_mean": after_mean,
                "delta_mean": after_mean - before_mean,
                "recording_count": len(baseline),
            }
    return summary


def build_quality_batch(
    annotations_directory: Path,
    baseline_scores_directory: Path,
    candidate_scores_directory: Path,
    output_directory: Path,
) -> Path:
    """Create a new report directory; existing destinations are never overwritten."""
    if output_directory.exists():
        raise FileExistsError(f"Quality bundle already exists: {output_directory}")
    annotation_paths = sorted(annotations_directory.glob("*.json"))
    if not annotation_paths:
        raise ValueError(f"No annotation JSON files found in {annotations_directory}")

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_directory.name}-", dir=output_directory.parent))
    try:
        recordings: list[dict[str, Any]] = []
        for annotation_path in annotation_paths:
            annotation = QualityAnnotation.model_validate_json(annotation_path.read_text())
            baseline_path = baseline_scores_directory / f"{annotation.recording_id}.json"
            candidate_path = candidate_scores_directory / f"{annotation.recording_id}.json"
            if not baseline_path.is_file() or not candidate_path.is_file():
                raise FileNotFoundError(
                    f"Missing baseline or candidate score for recording_id={annotation.recording_id}"
                )
            baseline_score = SongScore.model_validate_json(baseline_path.read_text())
            candidate_score = SongScore.model_validate_json(candidate_path.read_text())
            baseline_report = evaluate_quality_layers(baseline_score, annotation)
            candidate_report = evaluate_quality_layers(candidate_score, annotation)
            recording_directory = temporary / "sonifications" / annotation.recording_id
            baseline_audio = render_quality_sonifications(
                baseline_score, annotation, recording_directory / "baseline"
            )
            candidate_audio = render_quality_sonifications(
                candidate_score, annotation, recording_directory / "candidate"
            )
            recordings.append({
                "recording_id": annotation.recording_id,
                "annotation_source_sha256": annotation.source_sha256,
                "baseline": {layer: baseline_report[layer] for layer in LAYERS},
                "candidate": {layer: candidate_report[layer] for layer in LAYERS},
                "delta": {
                    layer: _numeric_delta(baseline_report[layer], candidate_report[layer])
                    for layer in LAYERS
                },
                "human_review": candidate_report["human_review"],
                "sonifications": {
                    "baseline": {key: f"sonifications/{annotation.recording_id}/baseline/{value}" for key, value in baseline_audio.items()},
                    "candidate": {key: f"sonifications/{annotation.recording_id}/candidate/{value}" for key, value in candidate_audio.items()},
                },
            })

        report = {
            "schema_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "recording_count": len(recordings),
            "summary": {layer: _layer_summary(recordings, layer) for layer in LAYERS},
            "recordings": recordings,
        }
        (temporary / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        temporary.rename(output_directory)
        return output_directory / "report.json"
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
