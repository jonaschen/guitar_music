import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("known_events", Path(__file__).resolve().parents[1]/"scripts/diagnose_known_events.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def test_six_independent_controls_write_all_artifacts_and_preserve_failures(tmp_path):
    output=tmp_path/"diagnostic"
    report=diagnostic.run(output)
    assert len(report["cases"]) == 6
    assert report["passed"]+report["failed"] == 6
    for case in report["cases"]:
        for file in ("reference.json","score.json","manifest.json","performance.mid","report.json"):
            assert (output/case["name"]/file).is_file()
        assert "error" not in case
        assert case["score_unchanged"]
    with pytest.raises(FileExistsError):
        diagnostic.run(output)


def test_comparison_detects_pitch_missing_note_and_timing_not_just_counts():
    ref=[dict(track="melody",pitch=60,start=0,end=.5)]
    assert not diagnostic.compare(ref,ref,.001)
    assert diagnostic.compare(ref,[dict(track="melody",pitch=61,start=0,end=.5)],.001)
    assert diagnostic.compare(ref,[dict(track="melody",pitch=60,start=.002,end=.5)],.001)
    assert diagnostic.compare(ref,[],.001)
