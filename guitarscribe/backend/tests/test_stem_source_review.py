import numpy as np
import pytest
import soundfile as sf

from app.evaluation.stem_source_review import digest, review
from app.models.melody_contour import MelodyContour


def fixtures(tmp_path):
    source = tmp_path / "job"
    source.mkdir()
    signal = np.sin(2*np.pi*440*np.arange(8000)/8000)*.5
    for name,gain in [("analysis-source",1),("vocal-stem",.5),("accompaniment-stem",.25)]:
        sf.write(source / f"{name}.wav",signal*gain,8000,subtype="FLOAT")
    contour = MelodyContour(source_artifact_kind="audio",source_artifact_sha256=digest(source / "vocal-stem.wav"),
        source_start=0,source_end=1,hop_seconds=.02,frequencies_hz=(440,)*50,voiced_probabilities=(.9,)*50)
    (source / "melody-contour.json").write_text(contour.model_dump_json())
    return source


def test_aligned_excerpts_preserve_relative_level_and_sources(tmp_path):
    source = fixtures(tmp_path)
    before = {p.name:digest(p) for p in source.iterdir()}
    output = tmp_path / "review"
    report = review(source,output,[("test",.2,.4)])
    assert report["shared_gain"] == 1
    assert report["contour_source_verified"] is True
    original,rate = sf.read(output / "test-original.wav")
    vocal,_ = sf.read(output / "test-vocal.wav")
    assert len(original) == 1600 and rate == 8000
    assert vocal == pytest.approx(original*.5,abs=4e-5)
    assert {p.name:digest(p) for p in source.iterdir()} == before
    with pytest.raises(FileExistsError):
        review(source,output,[("test",.2,.4)])


def test_rejects_hash_mismatch_and_invalid_windows(tmp_path):
    source = fixtures(tmp_path)
    with pytest.raises(ValueError,match="windows"):
        review(source,tmp_path / "bad",[("test",0,2)])
    with pytest.raises(ValueError,match="labels"):
        review(source,tmp_path / "bad",[("../test",0,.2)])
    sf.write(source / "vocal-stem.wav",np.zeros(8000),8000)
    with pytest.raises(ValueError,match="hash"):
        review(source,tmp_path / "bad",[("test",0,.2)])
    assert not (tmp_path / "bad").exists()
