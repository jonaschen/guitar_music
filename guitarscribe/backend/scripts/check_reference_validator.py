"""Replay frozen annotations and cached predictions; no inference or audio upload."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import mir_eval

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.annotations import QualityAnnotation
from app.evaluation.quality_report import evaluate_quality_layers
from app.models.analysis import BeatInfo, ChordEvent
from app.models.score import SongScore, AnalysisSummary


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(root, entry):
    path = root / entry["path"]
    if sha(path) != entry["sha256"]:
        raise ValueError(f"Frozen input changed: {entry['path']}")
    return path


def controls(annotation):
    down = {p.time for p in annotation.downbeats}
    original = SongScore(
        analysis=AnalysisSummary(bpm=annotation.tempo_bpm or 0),
        beats=[BeatInfo(time=p.time, beat=1 if p.time in down else 2, measure=1)
               for p in annotation.beats],
        chords=[ChordEvent(id=f"ref-{i}", start=c.start, end=c.end, symbol=c.label)
                for i, c in enumerate(annotation.chords)],
    )
    yield "identity", original
    half = original.model_copy(deep=True)
    half.beats = half.beats[::2]
    yield "half", half
    double = original.model_copy(deep=True)
    double.beats = sorted(double.beats + [BeatInfo(time=(a.time+b.time)/2, beat=2, measure=1)
                          for a, b in zip(original.beats, original.beats[1:])], key=lambda b: b.time)
    yield "double", double
    phase = original.model_copy(deep=True)
    for i, b in enumerate(phase.beats):
        b.beat = 1 if i > 0 and original.beats[i-1].beat == 1 else 2
    yield "bar_phase", phase
    dropout = original.model_copy(deep=True)
    middle = (annotation.excerpt_start + annotation.excerpt_end) / 2
    dropout.beats = [b for b in dropout.beats if not middle-2 <= b.time < middle+2]
    yield "dropout", dropout
    wrong = original.model_copy(deep=True)
    roots = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    for c in wrong.chords:
        if c.symbol in {"N", "X"}:
            continue
        root, quality, extensions, bass = mir_eval.chord.split(c.symbol)
        c.symbol = mir_eval.chord.join(roots[(mir_eval.chord.pitch_class_to_semitone(root)+1)%12],
                                      quality, extensions, bass)
    yield "wrong_root", wrong
    fragmented = original.model_copy(deep=True)
    fragmented.chords = []
    for c in original.chords:
        mid = (c.start+c.end)/2
        fragmented.chords.extend([c.model_copy(update={"end": mid}),
                                  c.model_copy(update={"id": c.id+"-split", "start": mid})])
    yield "fragmentation", fragmented


def expected(name, report):
    t, c = report["timing"], report["chord"]
    near = lambda a, b: abs(a-b) < 1e-8
    if name == "identity":
        return all(near(v, 1) for v in [t["beat_f_measure"], t["beat_cml_total"],
                                       t["downbeat_f_measure"], c["root_weighted_accuracy"]])
    if name in {"half", "double"}:
        ratio = .5 if name == "half" else 2
        return abs(t["beat_count_ratio"]-ratio) < .05 and t["beat_cml_total"] < .1 and t["beat_aml_total"] > .9
    if name == "bar_phase":
        return near(t["beat_f_measure"], 1) and t["downbeat_f_measure"] < .1
    if name == "dropout":
        return t["beat_cml_continuous"] < .7 and t["beat_f_measure"] < .98
    if name == "wrong_root":
        return near(t["beat_f_measure"], 1) and c["root_weighted_accuracy"] < .1
    if name == "fragmentation":
        return near(c["root_weighted_accuracy"], 1) and near(c["fragmentation_ratio"], 2)
    raise ValueError(name)


def run(root, plan_path, output):
    if output.exists():
        raise FileExistsError(output)
    plan = json.loads(plan_path.read_text())
    result = {"schema_version": "1.0", "plan_sha256": sha(plan_path),
              "reference_required": True, "product_accuracy_claim": False,
              "controls": [], "cached_predictions": []}
    for case in plan["cases"]:
        annotation = QualityAnnotation.model_validate_json(checked(root, case["annotation"]).read_text())
        audio = checked(root, case["audio"])
        if sha(audio) != annotation.source_sha256:
            raise ValueError("Annotation belongs to a different audio source")
        for name, score in controls(annotation):
            report = evaluate_quality_layers(score, annotation)
            result["controls"].append({"recording_id": annotation.recording_id, "mutation": name,
                                      "expected_detected": expected(name, report),
                                      "timing": report["timing"], "chord": report["chord"]})
        for entry in case["estimates"]:
            score = SongScore.model_validate_json(checked(root, entry).read_text())
            report = evaluate_quality_layers(score, annotation)
            result["cached_predictions"].append({"recording_id": annotation.recording_id,
                                                "engine": entry["name"],
                                                **{layer: report[layer] for layer in entry.get("layers", ["timing", "chord"])}})
    result["all_controls_detected"] = all(r["expected_detected"] for r in result["controls"])
    # Detect accidental input writes even if all metrics look plausible.
    for case in plan["cases"]:
        for entry in [case["annotation"], case["audio"], *case["estimates"]]:
            checked(root, entry)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as target:
        json.dump(result, target, indent=2, allow_nan=False)
        target.write("\n")
    print(json.dumps({"controls": len(result["controls"]), "passed": sum(x["expected_detected"] for x in result["controls"]),
                      "cached_predictions": len(result["cached_predictions"]), "report": str(output)}))
    return 0 if result["all_controls_detected"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.root, args.plan, args.output))
