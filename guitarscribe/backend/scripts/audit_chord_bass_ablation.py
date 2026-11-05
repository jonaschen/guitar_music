"""Re-evaluate saved ablation events and decisions without building or inferring."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_chord_bass_ablation import clipped_events, decision, historical_events, parity, projected_events, sha
from app.evaluation.annotations import QualityAnnotation
from app.evaluation.chord_errors import diagnose_chord_errors
from app.models.analysis import ChordEvent
from app.models.score import SongScore


def audit(root, plan_path, output):
    plan = json.loads(plan_path.read_text())
    saved = json.loads((output/"result.json").read_text())
    manifest = json.loads((output/"before-inference-manifest.json").read_text())
    if saved["plan_sha256"] != sha(plan_path) or saved["manifest_sha256"] != sha(output/"before-inference-manifest.json"):
        raise ValueError("Plan/manifest hash mismatch")
    if manifest["runner_sha256"] != sha(Path(__file__).with_name("run_chord_bass_ablation.py")):
        raise ValueError("Runner changed since inference")
    prep = manifest["preparation"]
    rows = []
    for case, saved_row in zip(plan["inputs"], saved["sources"], strict=True):
        rid = case["recording_id"]
        if rid != saved_row["recording_id"]:
            raise ValueError("Source ordering changed")
        for key in ("audio", "annotation", "estimate", "raw_cache"):
            if sha(root/case[key]["path"]) != case[key]["sha256"]:
                raise ValueError(f"Source hash mismatch: {rid}/{key}")
        score = SongScore.model_validate_json((root/case["estimate"]["path"]).read_text())
        ann = QualityAnnotation.model_validate_json((root/case["annotation"]["path"]).read_text())
        cached_raw = [ChordEvent.model_validate(e) for e in json.loads((root/case["raw_cache"]["path"]).read_text())["chords"]]
        row = {"recording_id": rid}
        for variant in ("baseline", "candidate"):
            events = json.loads((output/(rid+"-"+variant+"-events.json")).read_text())
            if events["library_sha256"] != prep["builds"][variant]["library_sha256"]:
                raise ValueError("Unexpected event library provenance")
            raw = historical_events(events["raw_events"], prep["audio"][rid]["duration_seconds"], case["historical_decoder"])
            projected = projected_events(raw, case)
            report = diagnose_chord_errors(score.model_copy(update={"chords": projected}), ann)
            disk_report = json.loads((output/(rid+"-"+variant+"-diagnostic.json")).read_text())
            if report != disk_report or report["summary"] != saved_row[variant]["summary"] or report["boundaries"] != saved_row[variant]["boundaries"]:
                raise ValueError(f"Saved diagnostic changed: {rid}/{variant}")
            row[variant] = {"summary": report["summary"], "boundaries": report["boundaries"]}
            if variant == "baseline":
                tol = plan["baseline_gate"]["time_absolute_tolerance_seconds"]
                gates = {"complete_historical_decoder": parity(cached_raw, raw, tol),
                         "fixed_domain_raw": parity(clipped_events(cached_raw, *case["interval"]), clipped_events(raw, *case["interval"]), tol),
                         "historical_projected_score": parity(score.chords, projected, tol)}
                if gates != saved_row["parity"] or not all(g["passed"] for g in gates.values()):
                    raise ValueError("Baseline comparison no longer passes")
        rows.append(row)
    verdict = decision(rows, plan["success"])
    if verdict != saved["decision"]:
        raise ValueError("Saved decision is not reproducible")
    return {"verified_sources": len(rows), "verified_diagnostics": 2*len(rows), "all_baseline_gates_pass": True,
            "outcome": verdict["outcome"], "new_inferences": 0, "writes": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.root, args.plan, args.output)))
