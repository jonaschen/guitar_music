import json

import pytest
import soundfile as sf

from app.evaluation.contour_review import render_review


def source_file(tmp_path):
    source = tmp_path / "frames.json"
    source.write_text(json.dumps({
        "frame_hop_seconds": 0.02, "analysis_context": [22, 23],
        "audition": [22.1, 22.9],
        "frames": [{"time": 22 + i * 0.02, "hz": 440,
                    "voiced_probability": 0.8} for i in range(50)],
    }))
    return source


def test_review_preserves_source_and_absolute_timing(tmp_path):
    source = source_file(tmp_path)
    before = source.read_bytes()
    output = tmp_path / "review"
    report = render_review(source, output)
    assert source.read_bytes() == before
    assert report["notes"][0]["midi"] == 69
    assert report["notes"][0]["start"] == 22
    assert report["notes"][0]["end"] == 23
    # The renderer floors frame counts; allow one sample plus float error.
    assert sf.info(output / "decoded-notes.wav").duration == pytest.approx(0.8, abs=1/16000 + 1e-9)
    assert json.loads((output / "decoded-notes.json").read_text()) == report
    with pytest.raises(FileExistsError):
        render_review(source, output)


@pytest.mark.parametrize("invalid", ["spacing", "long_context", "frequency"])
def test_invalid_source_does_not_create_output(tmp_path, invalid):
    source = source_file(tmp_path)
    data = json.loads(source.read_text())
    if invalid == "spacing":
        data["frames"][3]["time"] += 0.01
    elif invalid == "long_context":
        data["analysis_context"][1] = 100
    else:
        data["frames"][3]["hz"] = -1
    source.write_text(json.dumps(data))
    output = tmp_path / "review"
    with pytest.raises(ValueError):
        render_review(source, output)
    assert not output.exists()
