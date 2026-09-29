import json

import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError

from app.evaluation.contour_playback import export_audition, load_saved_contour, render_contour_playback
from app.evaluation.pitch_contour import render_pitch_contour
from app.models.melody_contour import MelodyContour


def saved_source(tmp_path):
    source = tmp_path / "frames.json"
    source.write_text(json.dumps({
        "analysis_context": [22, 23], "frame_hop_seconds": 0.1,
        "frames": [{"time": 22 + i * 0.1, "hz": None if i == 4 else 450 + i * 0.1,
                    "voiced_probability": 0.1} for i in range(10)],
    }))
    return source


def test_sidecar_roundtrip_preserves_all_pitch_and_confidence(tmp_path):
    source = saved_source(tmp_path)
    contour = load_saved_contour(source)
    restored = MelodyContour.model_validate_json(contour.model_dump_json())
    assert restored == contour
    assert restored.frequencies_hz[1] == 450.1  # No rounding to a MIDI note.
    assert restored.frequencies_hz[4] is None
    assert restored.voiced_probabilities == (0.1,) * 10  # No promotion/filtering.
    with pytest.raises(ValidationError):
        restored.hop_seconds = 0.2
    with pytest.raises(TypeError):
        restored.frequencies_hz[0] = 440


def test_export_matches_accepted_frame_hold_render_and_is_non_destructive(tmp_path):
    source = saved_source(tmp_path)
    before = source.read_bytes()
    original = load_saved_contour(source)
    direct = tmp_path / "direct.wav"
    render_pitch_contour(list(original.frequencies_hz), 0.1, 22, 22.1, 22.9,
                         direct, interpolate_frames=False)
    output = tmp_path / "export"
    export_audition(source, output, 22.1, 22.9)
    assert (output / "melody-contour.wav").read_bytes() == direct.read_bytes()
    restored = MelodyContour.model_validate_json((output / "contour.json").read_text())
    replay = tmp_path / "replayed.wav"
    render_contour_playback(restored, 22.1, 22.9, replay)
    assert replay.read_bytes() == direct.read_bytes()
    assert source.read_bytes() == before
    with pytest.raises(FileExistsError):
        export_audition(source, output, 22.1, 22.9)


def test_reference_crop_uses_absolute_source_offset(tmp_path):
    source = saved_source(tmp_path)
    reference = tmp_path / "source.wav"
    sf.write(reference, np.arange(16000) / 32000, 16000, subtype="PCM_16")
    output = tmp_path / "export"
    export_audition(source, output, 22.25, 22.75, reference)
    exported, rate = sf.read(output / "reference-vocals.wav")
    original, _ = sf.read(reference)
    np.testing.assert_array_equal(exported, original[4000:12000])
    assert rate == 16000


@pytest.mark.parametrize("problem", ["nan_hz", "negative_hz", "probability", "length", "grid", "coverage"])
def test_bad_source_rejected_before_output(tmp_path, problem):
    source = saved_source(tmp_path)
    data = json.loads(source.read_text())
    if problem == "nan_hz":
        data["frames"][0]["hz"] = float("nan")
    elif problem == "negative_hz":
        data["frames"][0]["hz"] = -1
    elif problem == "probability":
        data["frames"][0]["voiced_probability"] = 1.5
    elif problem == "length":
        data["frames"] = []
    elif problem == "grid":
        data["frames"][2]["time"] += 0.01
    else:
        data["analysis_context"][1] = 24
    source.write_text(json.dumps(data))
    output = tmp_path / "export"
    with pytest.raises(ValueError):
        export_audition(source, output, 22, 23)
    assert not output.exists()


def test_outside_context_and_wrong_reference_duration_rejected(tmp_path):
    source = saved_source(tmp_path)
    output = tmp_path / "export"
    with pytest.raises(ValueError):
        export_audition(source, output, 21, 23)
    reference = tmp_path / "short.wav"
    sf.write(reference, np.zeros(8000), 16000)
    with pytest.raises(ValueError):
        export_audition(source, output, 22, 23, reference)
    assert not output.exists()
