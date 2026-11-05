"""Replay a hash-frozen chord-error plan. Never runs models or uploads audio."""

import argparse
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.annotations import QualityAnnotation
from app.evaluation.chord_errors import diagnose_chord_errors
from app.models.score import SongScore


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked(root, entry):
    path = (root / entry["path"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Input path must stay within dataset root")
    if sha(path) != entry["sha256"]:
        raise ValueError(f"Frozen input changed: {entry['path']}")
    return path


def run(root: Path, plan_path: Path, output: Path):
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads(plan_path.read_text())
    plan_hash = sha(plan_path)
    reports = []
    seen = set()
    for case in plan["cases"]:
        recording_id = case["recording_id"]
        if recording_id in seen or Path(recording_id).name != recording_id or recording_id in {".", ".."}:
            raise ValueError("Recording IDs must be unique single path components")
        seen.add(recording_id)
        audio, annotation_path, score_path = [checked(root, case[k]) for k in ("audio", "annotation", "estimate")]
        annotation = QualityAnnotation.model_validate_json(annotation_path.read_text())
        score = SongScore.model_validate_json(score_path.read_text())
        if annotation.recording_id != recording_id or sha(audio) != annotation.source_sha256:
            raise ValueError("Reference/source identity mismatch")
        if case["interval"] != [annotation.excerpt_start, annotation.excerpt_end]:
            raise ValueError("Reference interval differs from frozen plan")
        # All current frozen inputs share a zero source origin. Refuse a future
        # cropped/transposed score rather than silently scoring different axes.
        if case["score_time_offset_seconds"] != 0 or score.song.source_start_seconds != 0:
            raise ValueError("Nonzero source offsets require an explicit time mapping")
        if score.key_context.transpose_semitones != 0:
            raise ValueError("Transposed scores require conversion to sounding source pitch")
        report = diagnose_chord_errors(score, annotation, boundary_tolerance=plan["boundary_tolerance_seconds"])
        report["inputs"] = case
        reports.append(report)
    if not reports:
        raise ValueError("Plan contains no cases")
    # Verify none of the frozen inputs changed during evaluation, before output.
    for case in plan["cases"]:
        for key in ("audio", "annotation", "estimate"):
            checked(root, case[key])
    if sha(plan_path) != plan_hash:
        raise ValueError("Plan changed during evaluation")
    output.mkdir(parents=True, exist_ok=False)
    for report in reports:
        with (output / f"{report['recording_id']}.json").open("x") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        with (output / f"{report['recording_id']}.csv").open("x", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(report["intervals"][0]))
            writer.writeheader()
            writer.writerows(report["intervals"])
    summary = {
        "schema_version": "1.0", "plan_sha256": plan_hash,
        "evaluator_sha256": sha(Path(__file__).resolve().parents[1] / "app/evaluation/chord_errors.py"),
        "mir_eval_version": importlib.metadata.version("mir_eval"),
        "new_model_inferences": 0, "external_requests": 0,
        "dataset_role": "development/regression; no generalization claim",
        "sources": [{"recording_id": r["recording_id"], "inputs": r["inputs"], **r["summary"],
                     "boundaries": {k: v for k, v in r["boundaries"].items()
                                    if k not in {"pairs", "unmatched_reference", "unmatched_estimate", "excluded_estimate_unknown_reference"}}}
                    for r in reports],
    }
    with (output / "summary.json").open("x") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"sources": len(reports), "output": str(output), "input_hashes_verified": True}))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.root, args.plan, args.output)
