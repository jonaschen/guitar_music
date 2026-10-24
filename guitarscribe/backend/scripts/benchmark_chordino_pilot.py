"""Run a fixed-parameter Chordino chord-only pilot on a GuitarSet protocol."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.benchmark_guitarset_pilot import reference, score_metrics  # noqa: E402
from app.analyzers.chords.chordino import ChordinoChordAnalyzer  # noqa: E402
from app.evaluation.quality_report import _mir_eval_chord_label  # noqa: E402
from app.models.analysis import BeatAnalysis  # noqa: E402
from app.models.audio import NormalizedAudio  # noqa: E402


PACKAGE_NAMES = ("vamp", "librosa", "numpy", "mir_eval", "soundfile", "pydantic")


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    return versions


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_new(path: Path, value: Any) -> None:
    """Create an artifact only if absent; never replace an existing result."""
    with path.open("x", encoding="utf-8") as destination:
        json.dump(value, destination, indent=2, ensure_ascii=False)
        destination.write("\n")


def unknown_label_summary(chord_analysis: Any, duration_seconds: float) -> dict[str, Any]:
    unknowns = []
    for event in chord_analysis.chords:
        if _mir_eval_chord_label(event.symbol) != "X":
            continue
        overlap = max(0.0, min(duration_seconds, event.end) - max(0.0, event.start))
        if overlap <= 0:
            continue
        unknowns.append({
            "symbol": event.symbol,
            "start": max(0.0, event.start),
            "end": min(duration_seconds, event.end),
            "duration_seconds": overlap,
        })
    return {
        "count": len(unknowns),
        "duration_seconds": sum(event["duration_seconds"] for event in unknowns),
        "events": unknowns,
        "note": "Labels mapped to X are unscorable/unknown, not major chords.",
    }


def load_protocol(path: Path) -> dict[str, Any]:
    protocol = json.loads(path.read_text(encoding="utf-8"))
    recordings = protocol.get("recordings") if isinstance(protocol, dict) else None
    if not isinstance(recordings, list) or not recordings:
        raise ValueError("Protocol must contain a non-empty recordings list")
    if any(not isinstance(name, str) or not name for name in recordings):
        raise ValueError("Every protocol recording must be a non-empty string")
    if len(set(recordings)) != len(recordings):
        raise ValueError("Protocol recording identifiers must be unique")
    return protocol


async def run(dataset: Path, protocol_path: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Output already exists; choose a new directory: {output}")
    protocol = load_protocol(protocol_path)
    # Atomic mkdir is also the final no-overwrite check against a concurrent run.
    output.mkdir(parents=True, exist_ok=False)

    analyzer = ChordinoChordAnalyzer()
    empty_beats = BeatAnalysis(
        bpm=120.0,
        time_signature="4/4",
        beats=[],
        downbeat_indices=[],
        confidence=0.0,
        engine="none",
        engine_version="none",
        warnings=["Chordino pilot does not infer or consume beat/downbeat timing."],
    )
    records: list[dict[str, Any]] = []

    for identifier in protocol["recordings"]:
        audio_path = dataset / f"{identifier}_mic.wav"
        jams_path = dataset / f"{identifier}.jams"
        row: dict[str, Any] = {
            "recording_id": identifier,
            "status": "failed",
            "audio_sha256": None,
            "inference_wall_seconds": None,
            "failure": None,
        }
        started = time.perf_counter()
        try:
            if audio_path.is_file():
                row["audio_sha256"] = sha256(audio_path)
            # Reuse the fixed GuitarSet reference loader; its beat points are
            # never passed to Chordino or the score used for chord metrics.
            annotation, _reference_beats, info = reference(jams_path, audio_path)
            row["audio_sha256"] = annotation.source_sha256
            audio = NormalizedAudio(
                path=audio_path,
                sample_rate=info.samplerate,
                channels=info.channels,
                duration_seconds=annotation.excerpt_end,
            )

            inference_started = time.perf_counter()
            chord_analysis = await analyzer.analyze(audio, empty_beats)
            row["inference_wall_seconds"] = time.perf_counter() - inference_started

            # score_metrics is shared with the GuitarSet pilot. Its empty-beat
            # timing fields are deliberately discarded; only chord metrics are
            # emitted by this chord-only benchmark.
            score, all_metrics = score_metrics(empty_beats, chord_analysis, annotation)
            chord_metrics = all_metrics["chord"]
            unknowns = unknown_label_summary(chord_analysis, annotation.excerpt_end)

            artifacts = {
                "chord_analysis": f"{identifier}.chord-analysis.json",
                "score": f"{identifier}.score.json",
                "metrics": f"{identifier}.metrics.json",
            }
            write_json_new(output / artifacts["chord_analysis"], chord_analysis.model_dump(mode="json"))
            write_json_new(output / artifacts["score"], score.model_dump(mode="json"))
            write_json_new(output / artifacts["metrics"], {
                "recording_id": identifier,
                "chord": chord_metrics,
                "unknown_labels": unknowns,
                "timing": "not evaluated; Chordino received an empty BeatAnalysis",
            })

            row.update({
                "status": "ok",
                "failure": None,
                "duration_seconds": annotation.excerpt_end,
                "evaluation_tier": annotation.evaluation_tier,
                "manual_edits": 0,
                "engine": chord_analysis.engine,
                "engine_version": chord_analysis.engine_version,
                "inference_wall_seconds": row["inference_wall_seconds"],
                "chord_metrics": chord_metrics,
                "unknown_labels": unknowns,
                "timing_metrics": "not evaluated",
                "artifacts": artifacts,
            })
        except Exception as error:
            row["failure"] = f"{type(error).__name__}: {error}"
        finally:
            row["wall_seconds"] = time.perf_counter() - started

        records.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    report = {
        "schema_version": "1.0",
        "protocol": protocol,
        "protocol_sha256": sha256(protocol_path),
        "dataset": str(dataset),
        "runner_sha256": sha256(Path(__file__)),
        "python_version": platform.python_version(),
        "package_versions": package_versions(),
        "analyzer": {
            "name": "chordino",
            "engine_version": "1.0",
            "parameters": "ChordinoChordAnalyzer defaults; no per-recording tuning",
            "beat_input": "empty BeatAnalysis; reference beat annotations are not supplied",
        },
        "records": records,
        "status": "failed" if any(record["status"] == "failed" for record in records) else "complete",
        "timing_metrics": "not reported as quality results; this pilot evaluates chord metrics only",
    }
    write_json_new(output / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(run(args.dataset, args.protocol, args.output))
    except Exception as error:
        parser.exit(2, f"benchmark_chordino_pilot: {type(error).__name__}: {error}\n")
    if report["status"] == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
