import json

from click.testing import CliRunner

from app.cli import main
from app.evaluation.metrics import beat_f_measure, evaluate_score, melody_pitch_accuracy
from app.models.analysis import BeatInfo, ChordEvent, MelodyNote
from app.models.score import AnalysisSummary, SongScore


def make_score() -> SongScore:
    return SongScore(
        analysis=AnalysisSummary(bpm=120),
        beats=[BeatInfo(time=0, beat=1, measure=1), BeatInfo(time=0.5, beat=2, measure=1)],
        chords=[ChordEvent(id="c", start=0, end=1, symbol="C")],
        melody=[MelodyNote(id="n", start=0.5, end=1, midi=72, note="C5")],
    )


def test_golden_metrics_score_perfect_match():
    annotation = {
        "bpm": 120,
        "beats": [0, 0.5],
        "chords": [{"start": 0, "end": 1, "symbol": "C"}],
        "melody": [{"start": 0.5, "midi": 72}],
    }

    assert evaluate_score(make_score(), annotation) == {
        "bpm_relative_error": 0.0,
        "beat_f_measure": 1.0,
        "chord_symbol_recall": 1.0,
        "melody_pitch_accuracy": 1.0,
    }


def test_golden_metrics_penalize_unmatched_beats_and_wrong_pitch():
    assert beat_f_measure([0, 0.5, 1], [0, 0.5]) == 0.8
    notes = [MelodyNote(id="wrong", start=0.5, end=1, midi=71, note="B4")]
    assert melody_pitch_accuracy(notes, [{"start": 0.5, "midi": 72}]) == 0.0


def test_evaluate_cli_prints_json_metrics(tmp_path):
    score_path = tmp_path / "score.json"
    annotation_path = tmp_path / "annotation.json"
    score_path.write_text(make_score().model_dump_json())
    annotation_path.write_text(json.dumps({"bpm": 120, "beats": [], "chords": [], "melody": []}))

    result = CliRunner().invoke(main, ["evaluate", str(score_path), str(annotation_path)])

    assert result.exit_code == 0
    assert json.loads(result.output)["bpm_relative_error"] == 0.0


def test_evaluate_cli_enforces_optional_quality_thresholds(tmp_path):
    score_path = tmp_path / "score.json"
    annotation_path = tmp_path / "annotation.json"
    mismatched_annotation_path = tmp_path / "mismatched-annotation.json"
    score_path.write_text(make_score().model_dump_json())
    annotation_path.write_text(json.dumps({"bpm": 120, "beats": [0, 0.5], "chords": [{"start": 0, "end": 1, "symbol": "C"}], "melody": [{"start": 0.5, "midi": 72}]}))
    mismatched_annotation_path.write_text(json.dumps({"bpm": 120, "beats": [0, 0.5], "chords": [{"start": 0, "end": 1, "symbol": "C"}], "melody": [{"start": 0.5, "midi": 71}]}))

    accepted = CliRunner().invoke(main, ["evaluate", str(score_path), str(annotation_path), "--max-bpm-relative-error", "0", "--min-beat-f-measure", "1", "--min-chord-symbol-recall", "1", "--min-melody-pitch-accuracy", "1"])
    rejected = CliRunner().invoke(main, ["evaluate", str(score_path), str(mismatched_annotation_path), "--min-melody-pitch-accuracy", "1"])

    assert accepted.exit_code == 0
    assert rejected.exit_code != 0
    assert "Golden quality gate failed" in rejected.output
