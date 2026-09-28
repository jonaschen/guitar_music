import numpy as np
import pytest
import soundfile as sf

from app.evaluation.melody_excerpt import write_melody_excerpt
from app.models.analysis import MelodyNote
from app.models.score import SongScore, SongInfo


def test_excerpt_keeps_alignment_overlaps_and_original_score(tmp_path):
    source = tmp_path / "input.wav"
    sf.write(source, np.zeros((32000, 2)), 8000)
    score = SongScore(song=SongInfo(duration_seconds=4), melody=[
        MelodyNote(id="a", start=0.5, end=2.5, midi=60, note="C4"),
        MelodyNote(id="b", start=1.5, end=3, midi=64, note="E4"),
    ])
    before = score.model_dump_json()
    output = tmp_path / "review"
    report = write_melody_excerpt(score, source, 1, 3, output)
    assert report["local_zero_equals_source_seconds"] == 1
    assert report["notes"][0]["local_start"] == 0
    assert report["notes"][0]["source_start"] == 0.5
    assert report["structure"]["overlap_seconds"] == 1
    for name in ("original.wav", "estimated-melody.wav"):
        assert sf.info(output / name).duration == 2
    assert sf.info(output / "original.wav").channels == 2
    assert score.model_dump_json() == before
    with pytest.raises(FileExistsError):
        write_melody_excerpt(score, source, 1, 3, output)
    with pytest.raises(ValueError):
        write_melody_excerpt(score, source, 1, 5, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()
