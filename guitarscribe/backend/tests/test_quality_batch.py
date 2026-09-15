import json

from click.testing import CliRunner

from app.cli import main
from app.evaluation.annotations import QualityAnnotation
from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.models.score import AnalysisSummary, SongScore


def make_annotation() -> QualityAnnotation:
    return QualityAnnotation(
        recording_id="legal-easy-01",
        source_sha256="a" * 64,
        rights_note="Original test fixture",
        difficulty="easy",
        excerpt_start=0,
        excerpt_end=2,
        tempo_bpm=120,
        beats=[{"time": value} for value in (0, 0.5, 1, 1.5)],
        downbeats=[{"time": 0}],
        chords=[{"start": 0, "end": 1, "label": "C"}, {"start": 1, "end": 2, "label": "Am"}],
        melody=[{"start": 0, "end": 0.5, "midi": 60}, {"start": 0.5, "end": 1, "midi": 62}],
    )


def make_score() -> SongScore:
    return SongScore(
        analysis=AnalysisSummary(bpm=120),
        beats=[BeatInfo(time=value, beat=index + 1, measure=1) for index, value in enumerate((0, 0.5, 1, 1.5))],
        chords=[
            ChordEvent(id="c1", start=0, end=1, symbol="C"),
            ChordEvent(id="c2", start=1, end=2, symbol="Am"),
        ],
        melody=[
            MelodyNote(id="m1", start=0, end=0.5, midi=60, note="C4"),
            MelodyNote(id="m2", start=0.5, end=1, midi=62, note="D4"),
        ],
    )


def test_quality_batch_creates_immutable_layered_bundle(tmp_path):
    annotations = tmp_path / "annotations"
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    output = tmp_path / "bundle"
    for directory in (annotations, baseline, candidate):
        directory.mkdir()

    annotation = make_annotation()
    baseline_score = make_score()
    baseline_score.melody[0] = MelodyNote(id="wrong", start=0, end=0.5, midi=61, note="C#4")
    candidate_score = make_score()
    (annotations / "fixture.json").write_text(annotation.model_dump_json())
    (baseline / "legal-easy-01.json").write_text(baseline_score.model_dump_json())
    (candidate / "legal-easy-01.json").write_text(candidate_score.model_dump_json())

    result = CliRunner().invoke(
        main,
        ["quality-batch", str(annotations), str(baseline), str(candidate), str(output)],
    )

    assert result.exit_code == 0, result.output
    report = json.loads((output / "report.json").read_text())
    assert "overall" not in report
    assert report["recording_count"] == 1
    item = report["recordings"][0]
    assert item["delta"]["melody"]["raw_pitch_accuracy"] > 0
    assert report["summary"]["melody"]["raw_pitch_accuracy"]["delta_mean"] > 0
    assert (output / item["sonifications"]["candidate"]["estimated_melody"]).is_file()

    repeated = CliRunner().invoke(
        main,
        ["quality-batch", str(annotations), str(baseline), str(candidate), str(output)],
    )
    assert repeated.exit_code != 0
    assert "already exists" in repeated.output


def test_quality_batch_removes_partial_bundle_when_a_score_is_missing(tmp_path):
    annotations = tmp_path / "annotations"
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    output = tmp_path / "bundle"
    for directory in (annotations, baseline, candidate):
        directory.mkdir()
    (annotations / "fixture.json").write_text(make_annotation().model_dump_json())

    result = CliRunner().invoke(
        main,
        ["quality-batch", str(annotations), str(baseline), str(candidate), str(output)],
    )

    assert result.exit_code != 0
    assert "Missing baseline or candidate score" in result.output
    assert not output.exists()
    assert not list(tmp_path.glob(".bundle-*"))
