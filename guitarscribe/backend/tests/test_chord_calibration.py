import json

from click.testing import CliRunner

from app.cli import main
from app.evaluation.annotations import QualityAnnotation
from app.models.analysis import ChordEvent
from app.models.score import Provenance, SongScore


def annotation() -> QualityAnnotation:
    return QualityAnnotation(
        recording_id="easy-01",
        source_sha256="b" * 64,
        rights_note="Original calibration fixture",
        difficulty="easy",
        excerpt_start=0,
        excerpt_end=2,
        chords=[{"start": 0, "end": 1, "label": "C"}, {"start": 1, "end": 2, "label": "G"}],
    )


def score(chords, threshold: float) -> SongScore:
    return SongScore(
        chords=chords,
        provenance=Provenance(
            chord_engine="chromagram",
            chord_engine_version="1.2",
            parameters={"decoder_change_threshold": threshold},
        ),
    )


def test_chord_calibration_reports_pareto_runs_without_combined_score(tmp_path):
    annotations = tmp_path / "annotations"
    runs = tmp_path / "runs"
    stable = runs / "stable"
    fragmented = runs / "fragmented"
    for directory in (annotations, stable, fragmented):
        directory.mkdir(parents=True)
    (annotations / "easy-01.json").write_text(annotation().model_dump_json())
    (stable / "easy-01.json").write_text(score([
        ChordEvent(id="c", start=0, end=1, symbol="C"),
        ChordEvent(id="g", start=1, end=2, symbol="G"),
    ], 0.12).model_dump_json())
    (fragmented / "easy-01.json").write_text(score([
        ChordEvent(id="c1", start=0, end=0.5, symbol="C"),
        ChordEvent(id="x", start=0.5, end=1, symbol="F#", needs_review=True),
        ChordEvent(id="g1", start=1, end=1.5, symbol="G"),
        ChordEvent(id="g2", start=1.5, end=2, symbol="Gm", needs_review=True),
    ], 0.05).model_dump_json())
    output = tmp_path / "calibration.json"

    result = CliRunner().invoke(main, ["chord-calibration", str(annotations), str(runs), str(output)])

    assert result.exit_code == 0, result.output
    report = json.loads(output.read_text())
    assert "overall" not in report
    assert report["selection_method"] == "pareto_frontier"
    assert report["objectives"]["acceptable_majmin_weighted_accuracy"] == "maximize"
    assert report["pareto_frontier"] == ["stable"]
    by_name = {run["name"]: run for run in report["runs"]}
    assert by_name["stable"]["decoder_parameters"]["decoder_change_threshold"] == 0.12
    assert by_name["stable"]["gates"]["fragmentation_1_25"] is True
    assert by_name["fragmented"]["gates"]["fragmentation_1_25"] is False
    assert report["human_audition_required"] is True


def test_chord_calibration_rejects_incomplete_runs(tmp_path):
    annotations = tmp_path / "annotations"
    runs = tmp_path / "runs"
    for directory in (annotations, runs / "a", runs / "b"):
        directory.mkdir(parents=True)
    (annotations / "easy-01.json").write_text(annotation().model_dump_json())
    output = tmp_path / "calibration.json"

    result = CliRunner().invoke(main, ["chord-calibration", str(annotations), str(runs), str(output)])

    assert result.exit_code != 0
    assert "Missing score" in result.output
    assert not output.exists()
