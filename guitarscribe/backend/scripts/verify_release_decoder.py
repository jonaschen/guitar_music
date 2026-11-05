"""Verify container decoder/runtime parity on frozen cached frames, without inference."""
import argparse
import asyncio
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np
import torch
from beat_this.model.postprocessor import Postprocessor

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analyzers.beats.beat_this_adapter import BeatThisBeatAnalyzer
from app.analyzers.beats.timing_diagnostics import BeatProjectionError
from app.models.audio import NormalizedAudio


def checked(root, entry):
    path = root / entry["path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError(f"Frozen input changed: {entry['path']}")
    return path


async def run(root, plan_path, output):
    if output.exists():
        raise FileExistsError(output)
    torch.set_num_threads(2)
    plan = json.loads(plan_path.read_text())
    rows = []
    for case in plan["cases"]:
        report = json.loads(checked(root, case["report"]).read_text())
        with np.load(checked(root, case["logits"])) as data:
            frames = tuple(torch.from_numpy(data[key]) for key in ("beat", "downbeat"))
        decoders = {name: Postprocessor(name) for name in ("minimal", "dbn")}
        matches = {}
        for name, decoder in decoders.items():
            actual = decoder(*frames)
            expected = report["decoders"][name]
            matches[name] = all([float(t) for t in values] == expected[key]
                                for key, values in zip(("beats", "downbeats"), actual))
        engine = BeatThisBeatAnalyzer(recovery_enabled=True, frame_predictor=lambda _: frames,
                                      primary_decoder=decoders["minimal"], recovery_decoder=decoders["dbn"])
        projected = None
        try:
            projected = await engine.analyze(NormalizedAudio(path=Path("unused-cached-frames"),
                                                             duration_seconds=case["duration"]))
        except BeatProjectionError:
            pass
        rows.append({"job": case["job"], "exact_decoder_match": matches,
                     "runtime_status": engine.parameters.get("beat_recovery_status"),
                     "runtime_beats": [b.model_dump(mode="json") for b in projected.beats] if projected else None,
                     "recovery_report": engine.recovery_report})
        print(case["job"], matches, engine.parameters.get("beat_recovery_status"), flush=True)
    result = {"schema_version": "1.0", "neural_inference_runs": 0,
              "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
              "versions": {name: version(name) for name in ("numpy", "scipy", "torch", "beat-this", "madmom")},
              "all_exact": all(all(row["exact_decoder_match"].values()) for row in rows), "rows": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as target:
        json.dump(result, target, indent=2, allow_nan=False)
        target.write("\n")
    return 0 if result["all_exact"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "plan", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.root, args.plan, args.output)))
