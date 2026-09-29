import hashlib
import json

import numpy as np
import pytest
import soundfile as sf

from app.evaluation.contour_controls import render_controls


def inputs(tmp_path):
    source, decoded = tmp_path / "source.json", tmp_path / "notes.json"
    data = {
        "frame_hop_seconds": 0.1, "analysis_context": [22, 23], "audition": [22, 23],
        "frames": [{"time": 22 + i * 0.1, "hz": None if i == 5 else 450}
                   for i in range(10)],
    }
    source.write_text(json.dumps(data))
    decoded.write_text(json.dumps({
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "analysis_context": [22, 23], "audition": [22, 23],
        "notes": [{"start": 22, "end": 22.5, "midi": 69},
                  {"start": 22.6, "end": 23, "midi": 69}],
    }))
    return source, decoded


def test_controls_preserve_sources_and_match_silence(tmp_path):
    source, decoded = inputs(tmp_path)
    original = (source.read_bytes(), decoded.read_bytes())
    output = tmp_path / "review"
    report = render_controls(source, decoded, output)
    assert (source.read_bytes(), decoded.read_bytes()) == original
    assert report["matched_voiced_mask"]
    for name in report["files"]:
        audio, sr = sf.read(output / name)
        assert len(audio) == sr
        assert not np.any(audio[8000:9600])
    # A/B differ only in interpolation; constant F0 produces identical bytes.
    assert (output / report["files"][0]).read_bytes() == (output / report["files"][1]).read_bytes()
    assert (output / report["files"][1]).read_bytes() != (output / report["files"][2]).read_bytes()
    with pytest.raises(FileExistsError):
        render_controls(source, decoded, output)


@pytest.mark.parametrize("problem", ["hash", "drop", "fill", "overlap", "off_grid", "nan", "window"])
def test_controls_reject_confounded_comparisons(tmp_path, problem):
    source, decoded = inputs(tmp_path)
    saved = json.loads(decoded.read_text())
    if problem == "hash":
        saved["source_sha256"] = "different"
    elif problem == "drop":
        saved["notes"][0]["end"] = 22.4
    elif problem == "fill":
        saved["notes"][0]["end"] = 22.6
    elif problem == "overlap":
        saved["notes"][0]["end"] = 22.7
    elif problem == "off_grid":
        saved["notes"][0]["end"] = 22.49
    elif problem == "nan":
        saved["notes"][0]["midi"] = float("nan")
    else:
        saved["audition"] = [22, 22.8]
    decoded.write_text(json.dumps(saved))
    output = tmp_path / "review"
    with pytest.raises(ValueError):
        render_controls(source, decoded, output)
    assert not output.exists()
