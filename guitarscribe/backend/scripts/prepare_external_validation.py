"""Prepare three licensed 15-second reference clips locally. No network calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.annotations import QualityAnnotation


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root, plan_path, output):
    output.mkdir(parents=True, exist_ok=False)
    plan = json.loads(plan_path.read_text())
    cases = []
    for case in plan["cases"]:
        audio = root / case["audio"]["path"]
        annotation_path = root / case["annotation"]["path"]
        if sha(audio) != case["audio"]["sha256"] or sha(annotation_path) != case["annotation"]["sha256"]:
            raise ValueError("Input no longer matches the frozen plan")
        ann = QualityAnnotation.model_validate_json(annotation_path.read_text())
        if ann.source_sha256 != sha(audio):
            raise ValueError("Reference/audio mismatch")
        info = sf.info(audio)
        if info.duration < 15:
            raise ValueError("Not enough audio for the frozen 0–15s clip")
        samples, rate = sf.read(audio, frames=15*info.samplerate)
        clip = output / (ann.recording_id+".wav")
        sf.write(clip, samples, rate, subtype="PCM_16")
        values = ann.model_dump(mode="json")
        values.update(evaluation_tier="smoke", source_file=clip.name, source_sha256=sha(clip),
                      excerpt_start=0, excerpt_end=15, melody=[], sections=[])
        values["beats"] = [b for b in values["beats"] if b["time"] < 15]
        values["downbeats"] = [b for b in values["downbeats"] if b["time"] < 15]
        values["chords"] = [dict(c, end=min(c["end"], 15)) for c in values["chords"] if c["start"] < 15]
        reference = QualityAnnotation.model_validate(values)
        ref_path = output / (ann.recording_id+".reference.json")
        ref_path.write_text(reference.model_dump_json(indent=2)+"\n")
        cases.append({"recording_id": ann.recording_id, "clip": clip.name, "clip_sha256": sha(clip),
                      "reference": ref_path.name, "reference_sha256": sha(ref_path),
                      "source_sha256": ann.source_sha256, "start": 0, "end": 15,
                      "sample_rate": rate, "frames": len(samples), "bytes": clip.stat().st_size})
    manifest = {"schema_version": "1.0", "provider": "Klangio", "uploaded": False,
                "plan_sha256": sha(plan_path), "license": "GuitarSet 1.1.0, CC BY 4.0",
                "attribution": "Xi et al., https://zenodo.org/records/3371780; cropped to 0–15s, PCM16; no other audio changes",
                "maximum_job_creations": 2*len(cases), "total_unique_audio_seconds": 15*len(cases),
                "requests": [{"path": "/beat-tracking", "query": {}},
                             {"path": "/chord-recognition", "query": {"vocabulary": "major-minor"}}],
                "upload_only": "Only listed WAV files, never reference labels or project data",
                "cost_status": "unverified; no paid request authorized", "cases": cases}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    print(json.dumps({k: manifest[k] for k in ["uploaded", "maximum_job_creations", "total_unique_audio_seconds"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["root", "plan", "output"]:
        parser.add_argument(key, type=Path)
    args = parser.parse_args()
    run(args.root, args.plan, args.output)
