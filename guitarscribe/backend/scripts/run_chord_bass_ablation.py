"""Bounded, isolated Chordino bass-contribution ablation; never changes live plugins."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.annotations import QualityAnnotation
from app.evaluation.chord_errors import diagnose_chord_errors
from app.models.score import SongScore


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def parity(expected, actual, tolerance):
    """Compare full playable event sequence, not just aggregate metrics."""
    if len(expected) != len(actual):
        return {"passed": False, "reason": "event_count", "expected": len(expected), "actual": len(actual)}
    for index, (e, a) in enumerate(zip(expected, actual)):
        if e.symbol != a.symbol or any(abs(getattr(e, k)-getattr(a, k)) > tolerance for k in ("start", "end")):
            return {"passed": False, "reason": "event", "index": index,
                    "expected": {k: getattr(e, k) for k in ("symbol", "start", "end")},
                    "actual": {k: getattr(a, k) for k in ("symbol", "start", "end")}}
    return {"passed": True, "event_count": len(expected)}


def decision(rows, rules):
    """All per-source guards are required, including on target recordings."""
    evaluated = []
    for row in rows:
        b, c = row["baseline"], row["candidate"]
        interior_b = b["summary"]["overlays_not_additive"]["wrong_root_interior_seconds"]
        interior_c = c["summary"]["overlays_not_additive"]["wrong_root_interior_seconds"]
        reduction = (interior_b-interior_c)/interior_b if interior_b > 0 else None
        changes = {metric+"_accuracy": c["summary"]["metrics"][metric]["accuracy"] - b["summary"]["metrics"][metric]["accuracy"]
                   for metric in ("root", "majmin")}
        changes["missed_plus_false_seconds"] = sum(c["summary"]["category_seconds"][k] - b["summary"]["category_seconds"][k]
                                                  for k in ("missed_chord", "false_chord"))
        for metric in ("precision", "recall"):
            old, new = b["boundaries"][metric], c["boundaries"][metric]
            changes["boundary_"+metric] = new-old if new is not None and old is not None else None
        guards = {
            "root": changes["root_accuracy"] >= -rules["all_source_max_root_accuracy_drop"]-1e-12,
            "majmin": changes["majmin_accuracy"] >= -rules["all_source_max_majmin_accuracy_drop"]-1e-12,
            "missed_false": changes["missed_plus_false_seconds"] <= rules["all_source_max_missed_plus_false_chord_seconds_increase"]+1e-12,
        }
        for metric in ("precision", "recall"):
            value = changes["boundary_"+metric]
            guards["boundary_"+metric] = value is not None and value >= -rules["all_source_max_boundary_"+metric+"_drop"]-1e-12
        evaluated.append({"recording_id": row["recording_id"], "changes": changes, "guards": guards,
                          "interior_wrong_root_relative_reduction": reduction,
                          "improved": reduction is not None and reduction >= rules["interior_wrong_root_min_relative_reduction"]-1e-12})
    target = [r for r in evaluated if r["recording_id"] == rules["target_guitarset"]]
    target_passed = len(target) == 1 and target[0]["improved"]
    hu33_improved = sum(r["improved"] for r in evaluated if r["recording_id"].startswith("SWD_HU33_"))
    passed = target_passed and hu33_improved >= rules["hu33_min_improved_sources"] and all(all(r["guards"].values()) for r in evaluated)
    return {"passed": bool(passed), "target_passed": bool(target_passed), "hu33_improved_count": hu33_improved,
            "sources": evaluated, "outcome": "eligible_for_independent_confirmation_only" if passed else "reject_fixed_ablation"}


def worker(config_path):
    # Each library runs in a fresh process: Vamp host caches loaded libraries.
    import librosa
    import vamp
    from app.analyzers.chords.chordino import decode_chord_events
    config = json.loads(Path(config_path).read_text())
    library = Path(vamp.vampyhost.get_library_for("nnls-chroma:chordino")).resolve()
    if library != Path(config["library"]).resolve() or sha(library) != config["library_sha256"]:
        raise ValueError("Vamp resolved an unexpected plugin")
    if sha(config["audio"]) != config["audio_sha256"]:
        raise ValueError("Audio changed before inference")
    started = time.monotonic()
    y, sr = librosa.load(config["audio"], sr=44100)
    data = vamp.collect(y, sr, "nnls-chroma:chordino")
    events = decode_chord_events(data["list"], config["duration_seconds"])
    write(config["output"], {"chords": [c.model_dump(mode="json") for c in events],
                            "raw_events": [{"timestamp": float(e["timestamp"]), "label": e["label"]} for e in data["list"]],
                            "inference_seconds": time.monotonic()-started, "library_sha256": sha(library)})


def historical_events(raw_events, duration, decoder):
    from app.models.analysis import ChordEvent
    from app.analyzers.chords.chordino import decode_chord_events
    if decoder == "audio-intersection-v1":
        return decode_chord_events(raw_events, duration)
    if decoder != "unbounded-v1":
        raise ValueError("Unknown historical decoder")
    return [ChordEvent(id=str(i), start=e["timestamp"],
                       end=raw_events[i+1]["timestamp"] if i+1 < len(raw_events) else duration,
                       symbol=e["label"])
            for i, e in enumerate(raw_events) if e["label"] != "N"]


def projected_events(events, case):
    from app.models.analysis import ChordEvent
    from scripts.benchmark_guitarset_pilot import merged
    if case["historical_score_projection"] == "identity":
        return events
    if case["historical_score_projection"] != "guitarset-merged":
        raise ValueError("Unknown historical score projection")
    return [ChordEvent(id=str(i), start=r["start"], end=r["end"], symbol=r["label"])
            for i, r in enumerate(merged([e.model_dump() for e in events], 0, case["interval"][1], "symbol"))]


def clipped_events(events, start, end):
    return [e.model_copy(update={"start": max(start, e.start), "end": min(end, e.end)})
            for e in events if e.start < end and e.end > start]


def run_amended(root, plan, plan_path, output):
    """Resume frozen preparations and first raw result; do not spend another run on them."""
    from app.models.analysis import ChordEvent
    import soundfile as sf
    amendment = plan["comparison_amendment"]
    plan_hash = sha(plan_path)
    deadline = dt.datetime.fromisoformat(plan["deadline_utc"].replace("Z", "+00:00"))
    def remaining():
        seconds = (deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()
        if seconds <= 0:
            raise TimeoutError("Original deadline reached")
        return seconds
    def checked(entry):
        path = root/entry["path"]
        if sha(path) != entry["sha256"]:
            raise ValueError(f"Frozen input changed: {entry['path']}")
        return path
    checked(plan["input_plan"])
    for case in plan["inputs"]:
        for key in ("audio", "annotation", "estimate", "raw_cache"):
            checked(case[key])
    backend = Path(__file__).resolve().parents[1]
    if sha(backend/"scripts/benchmark_guitarset_pilot.py") != amendment["historical_projection_sha256"]:
        raise ValueError("Historical score projection changed")
    if sha(backend/"app/analyzers/chords/chordino.py") != amendment["current_decoder_sha256"]:
        raise ValueError("Current decoder changed")
    preparation = json.loads(checked(amendment["reuse_preparation"]).read_text())
    for build in preparation["builds"].values():
        library = Path(build["library"])
        if sha(library) != build["library_sha256"] or (library.parent/"chord.dict").exists():
            raise ValueError("Prepared plugin/dictionary changed")
        for name, digest in build["source_sha256"].items():
            if sha(library.parent/name) != digest:
                raise ValueError("Prepared source changed")
    for audio in preparation["audio"].values():
        if sha(audio["path"]) != audio["sha256"]:
            raise ValueError("Prepared audio changed")
    first_events = checked(amendment["reuse_baseline_events"])
    env = dict(os.environ)
    env["PYTHONPATH"] = "/home/jonas/.cache/guitarscribe-chordino-diagnostic/python"
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = str(plan["limits"]["threads"])
    write(output/"before-inference-manifest.json", {"plan_sha256": plan_hash, "runner_sha256": sha(__file__),
                                                  "preparation": preparation, "reused_event_sha256": sha(first_events)})
    rows = [{"recording_id": c["recording_id"]} for c in plan["inputs"]]
    for variant in ("baseline", "candidate"):
        for case, row in zip(plan["inputs"], rows):
            remaining()
            rid = case["recording_id"]
            build, audio = preparation["builds"][variant], preparation["audio"][rid]
            events_path = output/(rid+"-"+variant+"-events.json")
            if variant == "baseline" and rid == amendment["reuse_baseline_recording"]:
                shutil.copy2(first_events, events_path)
            else:
                config = {"audio": audio["path"], "audio_sha256": audio["sha256"],
                          "duration_seconds": audio["duration_seconds"], "library": build["library"],
                          "library_sha256": build["library_sha256"], "output": str(events_path)}
                config_path = output/(rid+"-"+variant+"-config.json")
                write(config_path, config)
                env["VAMP_PATH"] = str(Path(build["library"]).parent)
                with (output/(rid+"-"+variant+"-run.log")).open("x") as handle:
                    subprocess.run([sys.executable, str(Path(__file__).resolve()), "worker", str(config_path)],
                                   env=env, cwd=output, stdout=handle, stderr=subprocess.STDOUT,
                                   check=True, timeout=min(300, remaining()))
            result = json.loads(events_path.read_text())
            raw = historical_events(result["raw_events"], audio["duration_seconds"], case["historical_decoder"])
            events = projected_events(raw, case)
            reference = SongScore.model_validate_json(checked(case["estimate"]).read_text())
            cached_raw = [ChordEvent.model_validate(e) for e in json.loads(checked(case["raw_cache"]).read_text())["chords"]]
            if variant == "baseline":
                tolerance = plan["baseline_gate"]["time_absolute_tolerance_seconds"]
                domain = case["interval"]
                row["parity"] = {
                    "complete_historical_decoder": parity(cached_raw, raw, tolerance),
                    "fixed_domain_raw": parity(clipped_events(cached_raw, *domain), clipped_events(raw, *domain), tolerance),
                    "historical_projected_score": parity(reference.chords, events, tolerance),
                }
                write(output/(rid+"-parity.json"), row["parity"])
                if not all(r["passed"] for r in row["parity"].values()):
                    raise ValueError(f"Baseline comparison failed: {rid}")
                row["crop_audit"] = {
                    "original_audio_duration": sf.info(root/case["audio"]["path"]).duration,
                    "analysis_duration": audio["duration_seconds"], "evaluation_interval": domain,
                    "historical_raw_event_count": len(raw), "historical_raw_last_end": raw[-1].end,
                    "raw_slash_chord_count": sum("/" in e.symbol for e in raw),
                    "outside_evaluation_events": [{"start": e.start, "end": e.end, "symbol": e.symbol,
                        "excluded_seconds": (e.end-e.start)-max(0, min(e.end, domain[1])-max(e.start, domain[0]))}
                        for e in raw if e.start < domain[0] or e.end > domain[1]],
                }
                row["raw_baseline"] = [e.model_dump(mode="json") for e in raw]
            else:
                row["raw_change"] = {"baseline_event_count": len(row["raw_baseline"]), "candidate_event_count": len(raw),
                                     "first_difference": parity([ChordEvent.model_validate(e) for e in row["raw_baseline"]], raw, 1e-9)}
            write(output/(rid+"-"+variant+"-historical-raw.json"), [e.model_dump(mode="json") for e in raw])
            annotation = QualityAnnotation.model_validate_json(checked(case["annotation"]).read_text())
            report = diagnose_chord_errors(reference.model_copy(update={"chords": events}), annotation)
            write(output/(rid+"-"+variant+"-diagnostic.json"), report)
            row[variant] = {"summary": report["summary"], "boundaries": report["boundaries"], "inference_seconds": result["inference_seconds"]}
            print(json.dumps({"variant": variant, "recording_id": rid, "root": report["summary"]["metrics"]["root"]["accuracy"]}), flush=True)
    remaining()
    if sha(plan_path) != plan_hash:
        raise ValueError("Plan changed during experiment")
    for case in plan["inputs"]:
        for key in ("audio", "annotation", "estimate", "raw_cache"):
            checked(case[key])
    for row in rows:
        del row["raw_baseline"]
    result = {"plan_sha256": plan_hash, "manifest_sha256": sha(output/"before-inference-manifest.json"),
              "decision": decision(rows, plan["success"]), "sources": rows,
              "baseline_runs": len(rows), "reused_baseline_runs": 1, "candidate_runs": len(rows),
              "external_requests": 0, "product_modified": False, "all_original_input_hashes_verified_after": True}
    write(output/"result.json", result)
    print(json.dumps(result["decision"]), flush=True)


def run(root, plan_path, output):
    root, output, plan_path = root.resolve(), output.resolve(), plan_path.resolve()
    plan = json.loads(plan_path.read_text())
    plan_hash = sha(plan_path)
    output.mkdir(parents=True, exist_ok=False)
    deadline = dt.datetime.fromisoformat(plan["deadline_utc"].replace("Z", "+00:00"))
    def remaining():
        seconds = (deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()
        if seconds <= 0:
            raise TimeoutError("Frozen experiment deadline reached")
        return seconds
    def execute(command, cwd, log, env=None):
        with log.open("x") as handle:
            subprocess.run(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT,
                           check=True, timeout=min(remaining(), 300))
    try:
        remaining()
        if "comparison_amendment" in plan:
            return run_amended(root, plan, plan_path, output)
        if sha(root/plan["input_plan"]["path"]) != plan["input_plan"]["sha256"]:
            raise ValueError("Input plan changed")
        cases = plan["inputs"]
        if len(cases) > min(plan["limits"]["max_baseline_runs"], plan["limits"]["max_candidate_runs"]):
            raise ValueError("Input count exceeds inference cap")
        for case in cases:
            for key in ("audio", "annotation", "estimate"):
                if sha(root/case[key]["path"]) != case[key]["sha256"]:
                    raise ValueError("Frozen input hash mismatch")
        source = Path(plan["source"]["path"])
        if sha(source/"nnls-chroma.so") != plan["source"]["original_library_sha256"]:
            raise ValueError("Original plugin library changed")
        if sha("/usr/lib/x86_64-linux-gnu/libvamp-sdk.so") != plan["build"]["vamp_sdk_library_sha256"]:
            raise ValueError("Build SDK changed")
        if subprocess.check_output(["g++", "--version"], text=True).splitlines()[0] != plan["build"]["compiler"]:
            raise ValueError("Build compiler changed")
        for name, digest in plan["source"]["tracked_file_sha256"].items():
            if sha(source/name) != digest:
                raise ValueError("Frozen plugin source changed")
        builds = {}
        for variant in ("baseline", "candidate"):
            folder = output/variant
            folder.mkdir()
            for name in plan["source"]["tracked_file_sha256"]:
                target = folder/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source/name, target)
            if variant == "candidate":
                path = folder/"Chordino.cpp"
                old = path.read_text()
                marker = "for (int iBin = 0; iBin < 12; iBin++) {\n                tempchordvalue += m_chorddict[24 * iChord + iBin] * chroma[iBin];\n            }"
                if old.count(marker) != 1:
                    raise ValueError("Bass contribution patch does not uniquely match")
                new = old.replace(marker, "// Fixed ablation: zero contribution from bass bins 0..11.")
                path.write_text(new)
                (output/"candidate.patch").write_text("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile="a/Chordino.cpp", tofile="b/Chordino.cpp")))
            if (folder/"chord.dict").exists():
                raise ValueError("External dictionary would invalidate comparison")
            execute(plan["build"]["command"], folder, output/(variant+"-build.log"))
            library = folder/"nnls-chroma.so"
            builds[variant] = {"library": str(library), "library_sha256": sha(library),
                               "source_sha256": {name: sha(folder/name) for name in plan["source"]["tracked_file_sha256"]}}
        audio = {}
        audio_dir = output/"audio"
        audio_dir.mkdir()
        ffmpeg = shutil.which("ffmpeg")
        for case in cases:
            rid = case["recording_id"]
            path = root/case["audio"]["path"]
            if rid.startswith("SWD_HU33_"):
                target = audio_dir/(rid+".wav")
                execute([ffmpeg, "-nostdin", "-n", "-i", str(path), "-ar", "44100", "-ac", "1", "-sample_fmt", "s16", "-f", "wav", str(target)],
                        output, audio_dir/(rid+"-ffmpeg.log"))
                path = target
                duration = 45.0
            else:
                duration = case["interval"][1]
            audio[rid] = {"path": str(path), "sha256": sha(path), "duration_seconds": duration}
        env = dict(os.environ)
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            env[name] = str(plan["limits"]["threads"])
        python_path = "/home/jonas/.cache/guitarscribe-chordino-diagnostic/python"
        env["PYTHONPATH"] = python_path
        manifest = {"plan_sha256": plan_hash, "runner_sha256": sha(__file__), "builds": builds, "audio": audio,
                    "ffmpeg_sha256": sha(ffmpeg), "python": sys.version,
                    "packages": {name: importlib.metadata.version(name) for name in ("numpy", "librosa", "mir_eval", "soundfile")}}
        if sha(plan_path) != plan_hash:
            raise ValueError("Plan changed before inference")
        write(output/"before-inference-manifest.json", manifest)
        rows = [{"recording_id": case["recording_id"]} for case in cases]
        for variant in ("baseline", "candidate"):
            for case, row in zip(cases, rows):
                remaining()
                rid = case["recording_id"]
                config = {"audio": audio[rid]["path"], "audio_sha256": audio[rid]["sha256"],
                          "duration_seconds": audio[rid]["duration_seconds"],
                          "library": builds[variant]["library"], "library_sha256": builds[variant]["library_sha256"],
                          "output": str(output/(rid+"-"+variant+"-events.json"))}
                config_path = output/(rid+"-"+variant+"-config.json")
                write(config_path, config)
                env["VAMP_PATH"] = str(output/variant)
                execute([sys.executable, str(Path(__file__).resolve()), "worker", str(config_path)], output,
                        output/(rid+"-"+variant+"-run.log"), env)
                from app.models.analysis import ChordEvent
                result = json.loads(Path(config["output"]).read_text())
                reference = SongScore.model_validate_json((root/case["estimate"]["path"]).read_text())
                events = [ChordEvent.model_validate(e) for e in result["chords"]]
                if variant == "baseline":
                    row["parity"] = parity(reference.chords, events, plan["baseline_gate"]["time_absolute_tolerance_seconds"])
                    write(output/(rid+"-parity.json"), row["parity"])
                    if not row["parity"]["passed"]:
                        raise ValueError(f"Baseline failed event parity: {rid}")
                score = reference.model_copy(update={"chords": events})
                annotation = QualityAnnotation.model_validate_json((root/case["annotation"]["path"]).read_text())
                report = diagnose_chord_errors(score, annotation)
                write(output/(rid+"-"+variant+"-diagnostic.json"), report)
                row[variant] = {"summary": report["summary"], "boundaries": report["boundaries"], "inference_seconds": result["inference_seconds"]}
                print(json.dumps({"variant": variant, "recording_id": rid, "root": report["summary"]["metrics"]["root"]["accuracy"]}), flush=True)
        if sha(plan_path) != plan_hash:
            raise ValueError("Plan changed during experiment")
        for case in cases:
            for key in ("audio", "annotation", "estimate"):
                if sha(root/case[key]["path"]) != case[key]["sha256"]:
                    raise ValueError("Frozen input changed during experiment")
        result = {"plan_sha256": plan_hash, "manifest_sha256": sha(output/"before-inference-manifest.json"),
                  "decision": decision(rows, plan["success"]), "sources": rows,
                  "baseline_runs": len(cases), "candidate_runs": len(cases), "external_requests": 0,
                  "product_modified": False, "all_original_input_hashes_verified_after": True}
        write(output/"result.json", result)
        print(json.dumps(result["decision"]), flush=True)
    except Exception as exc:
        write(output/"failure.json", {"type": type(exc).__name__, "error": str(exc), "plan_sha256": plan_hash,
                                      "completed_event_artifacts": sorted(p.name for p in output.glob("*-events.json")),
                                      "candidate_inference_started": any(output.glob("*-candidate-config.json")),
                                      "action": "stop; no retry or parameter search"})
        raise


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "worker":
        worker(sys.argv[2])
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("root", type=Path)
        parser.add_argument("plan", type=Path)
        parser.add_argument("output", type=Path)
        args = parser.parse_args()
        run(args.root, args.plan, args.output)
