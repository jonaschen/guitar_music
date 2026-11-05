import copy

from app.models.analysis import ChordEvent
from scripts.run_chord_bass_ablation import decision, historical_events, parity, projected_events


def test_baseline_gate_rejects_timing_symbol_and_event_count_changes():
    event = ChordEvent(id="a", start=0, end=5, symbol="C")
    assert parity([event], [event], 1e-9)["passed"]
    assert not parity([event], [], 1e-9)["passed"]
    assert not parity([event], [event.model_copy(update={"start": .01})], 1e-9)["passed"]
    assert not parity([event], [event.model_copy(update={"symbol": "Cm"})], 1e-9)["passed"]


def fixture():
    baseline = {"summary": {
        "overlays_not_additive": {"wrong_root_interior_seconds": 10},
        "metrics": {name: {"accuracy": .5} for name in ("root", "majmin")},
        "category_seconds": {"missed_chord": 0, "false_chord": 0},
    }, "boundaries": {"precision": .5, "recall": .5}}
    rows = []
    for name in ("Funk2", "SWD_HU33_04", "SWD_HU33_18", "Rock1"):
        candidate = copy.deepcopy(baseline)
        candidate["summary"]["overlays_not_additive"]["wrong_root_interior_seconds"] = 8
        rows.append({"recording_id": name, "baseline": copy.deepcopy(baseline), "candidate": candidate})
    rules = {"target_guitarset": "Funk2", "hu33_min_improved_sources": 2,
             "interior_wrong_root_min_relative_reduction": .1,
             "all_source_max_root_accuracy_drop": .01, "all_source_max_majmin_accuracy_drop": .01,
             "all_source_max_missed_plus_false_chord_seconds_increase": .25,
             "all_source_max_boundary_precision_drop": .05, "all_source_max_boundary_recall_drop": .05}
    return rows, rules


def test_controls_and_target_recordings_must_both_obey_regression_guards():
    rows, rules = fixture()
    assert decision(rows, rules)["passed"]
    for index in (0, 3):
        changed = copy.deepcopy(rows)
        changed[index]["candidate"]["summary"]["metrics"]["root"]["accuracy"] = .48
        assert not decision(changed, rules)["passed"]


def test_interior_improvement_cannot_hide_missing_chords_or_boundary_collapse():
    rows, rules = fixture()
    rows[0]["candidate"]["summary"]["category_seconds"]["missed_chord"] = .3
    assert not decision(rows, rules)["passed"]
    rows, rules = fixture()
    rows[0]["candidate"]["boundaries"]["precision"] = None
    assert not decision(rows, rules)["passed"]


def test_improving_hu33_does_not_excuse_failure_on_funk2():
    rows, rules = fixture()
    rows[0]["candidate"]["summary"]["overlays_not_additive"]["wrong_root_interior_seconds"] = 9.5
    result = decision(rows, rules)
    assert result["hu33_improved_count"] == 2
    assert result["outcome"] == "reject_fixed_ablation"


def test_raw_gate_preserves_slash_and_padding_before_historical_projection():
    vamp = [{"timestamp": 0, "label": "N"}, {"timestamp": .2, "label": "C/E"},
            {"timestamp": 10.2, "label": "N"}]
    old = historical_events(vamp, 10, "unbounded-v1")
    assert old[0].symbol == "C/E"
    assert old[0].end == 10.2
    current = historical_events(vamp, 10, "audio-intersection-v1")
    assert current[0].end == 10
    projected = projected_events(old, {"historical_score_projection": "guitarset-merged", "interval": [0, 10]})
    assert projected[0].symbol == "C:maj"
    assert projected[0].end == 10
    assert not parity(old, projected, 1e-9)["passed"]
    # Projection equality alone cannot excuse a changed inversion.
    different_bass = [old[0].model_copy(update={"symbol": "C/G"})]
    other = projected_events(different_bass, {"historical_score_projection": "guitarset-merged", "interval": [0, 10]})
    assert parity(projected, other, 1e-9)["passed"]
    assert not parity(old, different_bass, 1e-9)["passed"]
