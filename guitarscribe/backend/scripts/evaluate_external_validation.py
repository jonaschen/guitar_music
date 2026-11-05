"""Score saved Klangio results against the exact local reference packet; no upload."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.annotations import QualityAnnotation
from app.evaluation.external_reference import import_klangio_results
from app.evaluation.quality_report import evaluate_quality_layers


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(packet, results, output):
    if output.exists():
        raise FileExistsError(output)
    manifest_path = packet / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    rows = []
    for case in manifest["cases"]:
        audio, reference = packet / case["clip"], packet / case["reference"]
        if sha(audio) != case["clip_sha256"] or sha(reference) != case["reference_sha256"]:
            raise ValueError("Trial packet has changed")
        ann = QualityAnnotation.model_validate_json(reference.read_text())
        if ann.source_sha256 != sha(audio):
            raise ValueError("Reference is for different audio")
        prefix = case["recording_id"]
        beat_path, chord_path = results / (prefix+".beats.json"), results / (prefix+".chords.json")
        # Require both outputs; missing files do not become successful empty responses.
        score = import_klangio_results(beats=json.loads(beat_path.read_text()),
                                       chords=json.loads(chord_path.read_text()), duration=case["end"]-case["start"])
        report = evaluate_quality_layers(score, ann)
        rows.append({"recording_id": prefix, "timing": report["timing"], "chord": report["chord"],
                     "unknown_chord_seconds": sum(c.end-c.start for c in score.chords if c.symbol == "X"),
                     "beat_result_sha256": sha(beat_path), "chord_result_sha256": sha(chord_path)})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as target:
        json.dump({"schema_version": "1.0", "manifest_sha256": sha(manifest_path),
                   "provenance": "Locally supplied results; remote job identity must be verified separately",
                   "external_output_is_ground_truth": False, "product_acceptance": "not_assessed",
                   "recordings": rows}, target, indent=2, allow_nan=False)
        target.write("\n")
    print(f"Evaluated {len(rows)} recordings: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["packet", "results", "output"]:
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    run(args.packet, args.results, args.output)
