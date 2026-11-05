import hashlib
import importlib.util
import json
from pathlib import Path

import mir_eval
import pytest

from app.evaluation.annotations import QualityAnnotation
from app.evaluation.chord_errors import diagnostic_label, diagnose_chord_errors
from app.evaluation.quality_report import evaluate_quality_layers
from app.models.analysis import ChordEvent
from app.models.score import SongScore


def inputs(reference, estimated, start=0, end=10):
    annotation = QualityAnnotation(
        recording_id="fixture", source_sha256="a" * 64, rights_note="Synthetic control",
        difficulty="easy", excerpt_start=start, excerpt_end=end,
        chords=[dict(start=a, end=b, label=c) for a, b, c in reference],
    )
    score = SongScore(chords=[ChordEvent(id=str(i), start=a, end=b, symbol=c)
                             for i, (a, b, c) in enumerate(estimated)])
    return score, annotation


def diagnose(reference, estimated, start=0, end=10):
    return diagnose_chord_errors(*inputs(reference, estimated, start, end))


@pytest.mark.parametrize("raw,expected", [
    ("C/E", "C:maj/3"), ("Cmaj7/B", "C:maj7/7"), ("Bbm7/Db", "Bb:min7/b3"),
    ("C:maj/E", "C:maj/3"), ("C:maj/3", "C:maj/3"), ("F/G", "F:maj/2"),
    ("N.C.", "N"), ("X", "X"), ("F♯m", "F#:min"),
])
def test_normalization_preserves_bass_and_quality(raw, expected):
    assert diagnostic_label(raw) == expected


@pytest.mark.parametrize("raw", ["", "unrecognized", "C/nope", "C:invalid"])
def test_invalid_labels_do_not_become_silence_or_disappear(raw):
    with pytest.raises((ValueError, mir_eval.chord.InvalidChordException)):
        diagnostic_label(raw)


def test_exclusive_categories_conserve_duration_without_double_counting():
    refs = [(0, 1, "X"), (1, 2, "C"), (2, 3, "N"), (3, 4, "C"), (4, 5, "N"),
            (5, 6, "C"), (6, 7, "C"), (7, 8, "C/E"), (8, 10, "C")]
    ests = [(0, 1, "C"), (1, 2, "X"), (2, 3, "N"), (3, 4, "N"), (4, 5, "C"),
            (5, 6, "D"), (6, 7, "Cm"), (7, 8, "C"), (8, 10, "C")]
    report = diagnose(refs, ests)
    s = report["summary"]
    assert sum(s["category_seconds"].values()) == pytest.approx(10)
    assert s["known_reference_seconds"] == 9
    assert s["label_error_seconds"] == 6
    assert s["category_seconds"]["wrong_root"] == 1
    assert s["category_seconds"]["same_root_wrong_quality"] == 1
    assert s["category_seconds"]["bass_only"] == 1
    assert s["metrics"]["root"]["scored_seconds"] == 9
    assert s["metrics"]["root"]["error_seconds"] == 4


def test_unknown_reference_gaps_are_not_silence_or_accuracy():
    report = diagnose([(2, 4, "C"), (6, 8, "G")], [(0, 10, "C")])
    s = report["summary"]
    assert s["reference_unknown_seconds"] == 6
    assert s["metrics"]["root"]["scored_seconds"] == 4
    assert s["metrics"]["root"]["accuracy"] == .5
    assert s["category_seconds"]["false_chord"] == 0
    missing = diagnose([], [(0, 10, "C")])["summary"]
    assert missing["metrics"]["root"]["accuracy"] is None
    assert missing["label_error_seconds"] == 0


def test_estimate_gap_is_a_miss_but_retains_gap_origin():
    report = diagnose([(0, 10, "C")], [(2, 8, "C")])
    assert report["summary"]["category_seconds"]["missed_chord"] == 4
    assert report["intervals"][0]["estimate_origin"] == "gap"
    assert report["intervals"][0]["estimate_raw"] is None


def test_slash_bass_is_separate_from_quality_including_non_chord_bass():
    report = diagnose([(0, 5, "F"), (5, 10, "C:maj/3")], [(0, 5, "F/G"), (5, 10, "C/E")])
    assert report["summary"]["category_seconds"]["bass_only"] == 5
    assert report["summary"]["category_seconds"]["same_root_wrong_quality"] == 0
    assert report["summary"]["category_seconds"]["exact_match"] == 5


def test_same_root_extensions_are_quality_errors_even_when_majmin_matches():
    report = diagnose([(0, 10, "C:7")], [(0, 10, "C")])["summary"]
    assert report["category_seconds"]["same_root_wrong_quality"] == 10
    assert report["metrics"]["majmin"]["accuracy"] == 1


def test_explicit_omitted_root_is_not_reinserted_by_mir_eval_default_bass():
    report = diagnose([(0, 10, "C:min7(*1)")], [(0, 10, "C:min7")])
    assert report["summary"]["category_seconds"]["same_root_wrong_quality"] == 10
    assert report["summary"]["overlays_not_additive"]["reference_omits_root_seconds"] == 10
    assert report["intervals"][0]["same_absolute_pitch_classes"] is False


def test_theoretical_root_error_can_have_identical_pitch_classes():
    report = diagnose([(0, 10, "B:hdim7/b3")], [(0, 10, "Dm6")])
    assert report["summary"]["category_seconds"]["wrong_root"] == 10
    assert report["summary"]["overlays_not_additive"]["wrong_root_shared_pitch_set_seconds"] == 10
    assert report["summary"]["overlays_not_additive"]["wrong_root_is_reference_tone_seconds"] == 10


def test_boundary_proximity_windows_are_a_union_not_double_counted():
    report = diagnose([(0, 5, "C"), (5, 5.2, "G"), (5.2, 10, "C")], [(0, 10, "D")])
    assert report["summary"]["category_seconds"]["wrong_root"] == 10
    assert report["summary"]["overlays_not_additive"]["wrong_root_interior_seconds"] == pytest.approx(9.3)


def test_out_of_majmin_vocabulary_is_orthogonal_to_root_error():
    report = diagnose([(0, 5, "C:dim7"), (5, 10, "C")], [(0, 10, "D")])["summary"]
    assert report["category_seconds"]["wrong_root"] == 10
    assert report["metrics"]["root"]["error_seconds"] == 10
    assert report["metrics"]["majmin"]["scored_seconds"] == 5
    assert report["metrics"]["majmin"]["accuracy"] == 0


def test_boundary_lag_is_signed_one_to_one_and_not_added_to_label_seconds():
    report = diagnose([(0, 5, "C"), (5, 10, "G")],
                      [(0, 5.1, "C"), (5.1, 5.2, "G"), (5.2, 10, "Am")])
    boundaries = report["boundaries"]
    assert boundaries["matched_count"] == 1
    assert len(boundaries["unmatched_estimate"]) == 1
    assert boundaries["pairs"][0]["lag_seconds"] == pytest.approx(.1)
    assert report["summary"]["label_error_seconds"] == pytest.approx(4.9)


def test_equivalent_segments_and_clip_endpoints_do_not_create_boundaries():
    report = diagnose([(0, 5, "C#"), (5, 20, "Db")],
                      [(0, 4, "Db:maj"), (4, 6, "C#"), (6, 20, "Db")], start=2, end=8)
    assert report["summary"]["category_seconds"]["exact_match"] == 6
    assert report["boundaries"]["reference_count"] == 0
    assert report["boundaries"]["estimated_count"] == 0


def test_transitions_inside_unknown_reference_are_excluded():
    report = diagnose([(0, 2, "C"), (8, 10, "G")], [(0, 4, "C"), (4, 10, "G")])
    assert report["boundaries"]["estimated_count"] == 0
    assert len(report["boundaries"]["excluded_estimate_unknown_reference"]) == 1


def test_historical_root_and_majmin_metrics_remain_comparable():
    score, reference = inputs([(0, 2, "C:maj/3"), (2, 4, "D:dim"), (4, 10, "N")],
                              [(0, 3, "C/E"), (3, 5, "G"), (6, 10, "N")])
    old = evaluate_quality_layers(score, reference)["chord"]
    new = diagnose_chord_errors(score, reference)["summary"]["metrics"]
    assert new["root"]["accuracy"] == pytest.approx(old["root_weighted_accuracy"])
    assert new["majmin"]["accuracy"] == pytest.approx(old["majmin_weighted_accuracy"])
    assert new["majmin"]["scored_seconds"] == pytest.approx(old["majmin_scored_seconds"])


def test_overlapping_or_nonfinite_data_is_rejected():
    with pytest.raises(ValueError, match="Overlapping"):
        diagnose([(0, 10, "C")], [(0, 6, "C"), (5, 10, "G")])
    score, ref = inputs([(0, 10, "C")], [(0, 10, "C")])
    ref.chords[0].end = float("inf")
    with pytest.raises(ValueError, match="finite"):
        diagnose_chord_errors(score, ref)


def load_runner():
    path = Path(__file__).parents[1] / "scripts/diagnose_cached_chord_errors.py"
    spec = importlib.util.spec_from_file_location("chord_error_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_plan(tmp_path):
    score, annotation = inputs([(0, 10, "C")], [(0, 10, "C")])
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"synthetic source identity; audio decoding is not used")
    annotation.source_sha256 = hashlib.sha256(audio.read_bytes()).hexdigest()
    (tmp_path / "annotation.json").write_text(annotation.model_dump_json())
    (tmp_path / "score.json").write_text(score.model_dump_json())
    def file(name):
        return {"path": name, "sha256": hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()}
    plan = {"boundary_tolerance_seconds": .25, "cases": [{
        "recording_id": "fixture", "audio": file("audio.wav"), "annotation": file("annotation.json"),
        "estimate": file("score.json"), "interval": [0, 10], "score_time_offset_seconds": 0}]}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    return path


def test_runner_preserves_inputs_and_refuses_output_overwrite(tmp_path):
    plan = frozen_plan(tmp_path)
    runner = load_runner()
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    summary = runner.run(tmp_path, plan, tmp_path / "out")
    assert summary["sources"][0]["label_error_seconds"] == 0
    assert (tmp_path / "out/fixture.csv").is_file()
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    with pytest.raises(FileExistsError):
        runner.run(tmp_path, plan, tmp_path / "out")


@pytest.mark.parametrize("corruption", ["audio", "annotation", "estimate", "offset", "interval", "recording_id"])
def test_runner_refuses_changed_or_misaligned_inputs_before_writing(tmp_path, corruption):
    path = frozen_plan(tmp_path)
    plan = json.loads(path.read_text())
    case = plan["cases"][0]
    if corruption in {"audio", "annotation", "estimate"}:
        (tmp_path / case[corruption]["path"]).write_text("changed")
    elif corruption == "offset":
        case["score_time_offset_seconds"] = 5
    elif corruption == "interval":
        case["interval"] = [1, 10]
    else:
        case["recording_id"] = "another-recording"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError):
        load_runner().run(tmp_path, path, tmp_path / "out")
    assert not (tmp_path / "out").exists()
