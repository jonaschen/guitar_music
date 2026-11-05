"""Cross-tabulate frozen dictionary availability and cached chord errors; no inference."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.chord_dictionary import CATEGORIES, DictionaryAvailability, cross_tabulate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root, plan_path, extraction, output):
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads(plan_path.read_text())
    plan_hash = sha(plan_path)
    for name in ("input_plan", "diagnostic_results"):
        if sha(root/plan[name]["path"]) != plan[name]["sha256"]:
            raise ValueError("Frozen input plan/results changed")
    inputs = json.loads((root/plan["input_plan"]["path"]).read_text())["cases"]
    previous = json.loads((root/plan["diagnostic_results"]["path"]).read_text())
    manifest = json.loads((extraction/"extraction-manifest.json").read_text())
    if manifest["plan_sha256"] != plan_hash or manifest["dictionary_sha256"] != sha(extraction/"dictionary.json"):
        raise ValueError("Extraction not bound to frozen plan")
    for name, digest in plan["source"]["files"].items():
        if sha(Path(plan["source"]["path"])/name) != digest:
            raise ValueError("Original plugin source changed")
    availability = DictionaryAvailability(json.loads((extraction/"dictionary.json").read_text()))
    reports, labels = [], {}
    for case, old in zip(inputs, previous["sources"], strict=True):
        rid = case["recording_id"]
        if old["recording_id"] != rid:
            raise ValueError("Recording order changed")
        for key in ("audio", "annotation", "estimate"):
            if sha(root/case[key]["path"]) != case[key]["sha256"]:
                raise ValueError("Frozen source changed")
        filename = rid+".json"
        path = root/previous["artifact_directory"]/filename
        if sha(path) != previous["artifact_sha256"][filename]:
            raise ValueError("Cached error intervals changed")
        intervals = json.loads(path.read_text())["intervals"]
        report = {"recording_id": rid, **cross_tabulate(intervals, availability)}
        if abs(report["wrong_root_seconds"]-old["category_seconds"]["wrong_root"]) > 1e-9:
            raise ValueError("Wrong-root seconds no longer match prior diagnostic")
        if abs(report["reference_seconds"]-old["duration_seconds"]) > 1e-9:
            raise ValueError("Reference seconds not conserved")
        reports.append(report)
        for interval in intervals:
            label = interval["reference_label"]
            row = labels.setdefault(label, {"label": label, "reference_seconds": 0.0, "wrong_root_seconds": 0.0,
                                           **availability.classify(label)})
            row["reference_seconds"] += interval["seconds"]
            row["wrong_root_seconds"] += interval["seconds"] if interval["category"] == "wrong_root" else 0.0
    aggregates = {}
    for group, selected in (("all", reports), ("GuitarSet", [r for r in reports if not r["recording_id"].startswith("SWD_")]),
                            ("HU33", [r for r in reports if r["recording_id"].startswith("SWD_")])):
        ref = sum(r["reference_seconds"] for r in selected)
        wrong = sum(r["wrong_root_seconds"] for r in selected)
        aggregates[group] = {"reference_seconds": ref, "wrong_root_seconds": wrong, "categories": {}}
        for name in CATEGORIES:
            value = {metric: sum(r["categories"][name][metric] for r in selected)
                     for metric in ("reference_seconds", "wrong_root_seconds")}
            value.update(reference_fraction=value["reference_seconds"]/ref,
                         wrong_root_fraction=value["wrong_root_seconds"]/wrong)
            aggregates[group]["categories"][name] = value
    hu33 = [r for r in reports if r["recording_id"].startswith("SWD_")]
    def majority(category):
        return aggregates["all"]["categories"][category]["wrong_root_fraction"] > .5 and sum(
            r["categories"][category]["wrong_root_fraction"] > .5 for r in hu33) >= 2
    strict, absent = majority("strict_label_match"), majority("candidate_pattern_absent")
    branch = ("strict_available_majority" if strict else "absent_majority" if absent else "otherwise")
    result = {
        "plan_sha256": plan_hash, "extraction_manifest_sha256": sha(extraction/"extraction-manifest.json"),
        "runner_sha256": sha(Path(__file__)),
        "classifier_sha256": sha(Path(__file__).resolve().parents[1]/"app/evaluation/chord_dictionary.py"),
        "dictionary_entries": manifest["entry_count"], "aggregates": aggregates,
        "sources": [{k: v for k, v in r.items() if k != "intervals"} for r in reports],
        "labels": sorted(labels.values(), key=lambda r: -r["wrong_root_seconds"]),
        "decision": {"branch": branch, "meaning": plan["decision_branches"][branch],
                     "strict_match_majority_hu33_sources": sum(r["categories"]["strict_label_match"]["wrong_root_fraction"] > .5 for r in hu33),
                     "absent_pattern_majority_hu33_sources": sum(r["categories"]["candidate_pattern_absent"]["wrong_root_fraction"] > .5 for r in hu33)},
        "new_inferences": 0, "external_requests": 0, "product_changed": False,
    }
    if sha(plan_path) != plan_hash:
        raise ValueError("Plan changed during evaluation")
    output.mkdir(parents=True, exist_ok=False)
    for report in reports:
        (output/(report["recording_id"]+".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    (output/"result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"sources": len(reports), "decision": result["decision"], "new_inferences": 0}))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("extraction", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.root, args.plan, args.extraction, args.output)
