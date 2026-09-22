"""Multi-run chord decoder comparison without an opaque aggregate score."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .annotations import QualityAnnotation
from .quality_report import evaluate_quality_layers
from ..models.score import SongScore


OBJECTIVES = {
    "majmin_weighted_accuracy": "maximize",
    "boundary_f_measure": "maximize",
    "fragmentation_error": "minimize",
    "review_event_ratio": "minimize",
}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _dominates(left: dict[str, float], right: dict[str, float]) -> bool:
    no_worse = []
    strictly_better = []
    for metric, direction in OBJECTIVES.items():
        if direction == "maximize":
            no_worse.append(left[metric] >= right[metric])
            strictly_better.append(left[metric] > right[metric])
        else:
            no_worse.append(left[metric] <= right[metric])
            strictly_better.append(left[metric] < right[metric])
    return all(no_worse) and any(strictly_better)


def build_chord_calibration(
    annotations_directory: Path,
    runs_directory: Path,
    output_file: Path,
) -> Path:
    """Compare score directories and retain all non-dominated configurations."""
    if output_file.exists():
        raise FileExistsError(f"Chord calibration report already exists: {output_file}")
    annotations = [
        QualityAnnotation.model_validate_json(path.read_text())
        for path in sorted(annotations_directory.glob("*.json"))
    ]
    if not annotations:
        raise ValueError(f"No annotation JSON files found in {annotations_directory}")
    run_directories = sorted(path for path in runs_directory.iterdir() if path.is_dir())
    if len(run_directories) < 2:
        raise ValueError("Chord calibration requires at least two run directories")

    runs: list[dict[str, Any]] = []
    for run_directory in run_directories:
        recordings = []
        decoder_parameters: dict[str, str | int | float | bool] | None = None
        engine_versions: set[str] = set()
        for annotation in annotations:
            score_path = run_directory / f"{annotation.recording_id}.json"
            if not score_path.is_file():
                raise FileNotFoundError(
                    f"Missing score for run={run_directory.name}, recording_id={annotation.recording_id}"
                )
            score = SongScore.model_validate_json(score_path.read_text())
            parameters = {
                key: value
                for key, value in score.provenance.parameters.items()
                if key.startswith("decoder_")
            }
            if decoder_parameters is None:
                decoder_parameters = parameters
            elif parameters != decoder_parameters:
                raise ValueError(f"Inconsistent decoder parameters within run={run_directory.name}")
            engine_versions.add(score.provenance.chord_engine_version)
            chord_metrics = evaluate_quality_layers(score, annotation)["chord"]
            recordings.append({"recording_id": annotation.recording_id, "metrics": chord_metrics})

        numeric_metrics = sorted({
            key
            for recording in recordings
            for key, value in recording["metrics"].items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        })
        summary = {
            metric: _mean([
                float(recording["metrics"][metric])
                for recording in recordings
                if isinstance(recording["metrics"].get(metric), (int, float))
                and not isinstance(recording["metrics"].get(metric), bool)
            ])
            for metric in numeric_metrics
        }
        summary["fragmentation_error"] = abs(summary.get("fragmentation_ratio", 0.0) - 1.0)
        summary.setdefault("majmin_weighted_accuracy", 0.0)
        summary.setdefault("boundary_f_measure", 0.0)
        summary.setdefault("review_event_ratio", 0.0)
        runs.append({
            "name": run_directory.name,
            "chord_engine_versions": sorted(engine_versions),
            "decoder_parameters": decoder_parameters or {},
            "recording_count": len(recordings),
            "summary": summary,
            "gates": {
                "fragmentation_1_25": all(
                    float(recording["metrics"].get("fragmentation_ratio", 0.0)) <= 1.25
                    for recording in recordings
                ),
            },
            "recordings": recordings,
        })

    frontier = [
        candidate["name"]
        for candidate in runs
        if not any(
            other["name"] != candidate["name"]
            and _dominates(other["summary"], candidate["summary"])
            for other in runs
        )
    ]
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_method": "pareto_frontier",
        "objectives": OBJECTIVES,
        "pareto_frontier": frontier,
        "human_audition_required": True,
        "runs": runs,
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return output_file
