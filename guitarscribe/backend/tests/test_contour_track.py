import numpy as np
import pytest
import soundfile as sf

from app.evaluation.contour_track import render_contour_track, save_contour_artifacts
from app.evaluation.pitch_contour import render_pitch_contour
from app.models.melody_contour import MelodyContour


def contour(values, hop=0.023219954648526078, offset=0):
    return MelodyContour(source_artifact_sha256="0" * 64, source_start=offset,
                         source_end=offset + len(values) * hop, hop_seconds=hop,
                         frequencies_hz=tuple(values), voiced_probabilities=(0.1,) * len(values))


@pytest.mark.parametrize("values,hop,offset", [
    ([440, 450.3, None, 470.1, 460] * 30, 512/22050, 0),
    ([440, None, 450], 0.13, 0.17),
    ([None] * 10, 0.1, 0),
    ([443.2, 665.1], 0.8, 0),  # Sustains exceed the write block size.
    ([440, None, 450], 1/16000, 0),  # Degenerate fade boundaries.
    ([440, None, 450], 2/16000, 0),
])
def test_streaming_matches_reference_frame_hold(tmp_path, values, hop, offset):
    saved = contour(values, hop, offset)
    direct, streamed = tmp_path / "direct.wav", tmp_path / "streamed.wav"
    render_pitch_contour(values, hop, offset, 0, saved.source_end, direct,
                         interpolate_frames=False)
    render_contour_track(saved, streamed)
    expected, sr = sf.read(direct)
    actual, rate = sf.read(streamed)
    assert sr == rate == 16000
    assert len(actual) == len(expected)
    # Grouped phase summation may move a PCM sample by one quantization unit.
    np.testing.assert_allclose(actual, expected, atol=1/32768 + 1e-9)


def test_artifacts_do_not_promote_silent_contour_to_playable_track(tmp_path):
    saved = contour([None] * 10)
    save_contour_artifacts(saved, tmp_path)
    assert MelodyContour.model_validate_json((tmp_path / "melody-contour.json").read_text()) == saved
    assert not (tmp_path / "melody-contour.wav").exists()


def test_failed_render_does_not_publish_partial_audio(tmp_path, monkeypatch):
    from app.evaluation import contour_track
    def failed(contour, path):
        path.write_bytes(b"unfinished")
        raise RuntimeError("render failed")
    monkeypatch.setattr(contour_track, "render_contour_track", failed)
    with pytest.raises(RuntimeError):
        save_contour_artifacts(contour([440] * 10), tmp_path)
    assert not (tmp_path / "melody-contour.wav").exists()
    assert (tmp_path / "melody-contour.json").is_file()
