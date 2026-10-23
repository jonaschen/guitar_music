from copy import deepcopy

import pytest

from app.evaluation.harmony_consensus import select_boundary_consensus


ROUTES = (
    ("analysis-source", "cqt"),
    ("analysis-source", "stft"),
    ("accompaniment-stem", "cqt"),
    ("accompaniment-stem", "stft"),
)


def report_with_candidates(candidates=(10.00, 10.02, 10.04, 10.06)):
    report = {"revision": "fixed", "sources": {}}
    for (source, method), candidate in zip(ROUTES, candidates):
        cluster = [candidate - 0.01, candidate + 0.01]
        report.setdefault("sources", {}).setdefault(source, {})[method] = [{
            "symbol": "G",
            "boundary": {
                "from": "C",
                "to": "G",
                "saved_time": 10.0,
                "persistent_crossing_clusters": [cluster],
            },
        }]
    return report


def test_accepts_one_aligned_consensus_and_reports_evidence():
    result = select_boundary_consensus(report_with_candidates())

    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["accepted"] is True
    assert row["reason"] == "unique_consensus"
    assert row["from"] == "C"
    assert row["to"] == "G"
    assert row["saved_time"] == 10.0
    assert row["target_time"] == pytest.approx(10.03)
    assert len(row["evidence"]["routes"]) == 4
    assert len(row["evidence"]["combinations_with_limits"]) == 1
    assert result["parameters"]["max_spread"] == 0.15
    assert result["parameters"]["max_shift"] == 0.45
    assert any("not independent ground truth" in item for item in result["limitations"])


def test_rejects_missing_route_even_when_other_three_align():
    report = report_with_candidates()
    report["sources"]["accompaniment-stem"]["stft"][0]["boundary"]["persistent_crossing_clusters"] = []

    row = select_boundary_consensus(report)["rows"][0]

    assert row["accepted"] is False
    assert row["target_time"] is None
    assert row["reason"] == "missing_route_evidence"
    assert row["evidence"]["missing_routes"] == [{"source": "accompaniment-stem", "method": "stft"}]


def test_rejects_multiple_valid_combinations():
    report = report_with_candidates()
    for source, method in ROUTES:
        boundary = report["sources"][source][method][0]["boundary"]
        boundary["persistent_crossing_clusters"] = [[9.99, 10.01], [10.04, 10.06]]

    row = select_boundary_consensus(report)["rows"][0]

    assert row["accepted"] is False
    assert row["target_time"] is None
    assert row["reason"] == "multiple_consensus_combinations"
    assert len(row["evidence"]["combinations_with_limits"]) > 1


def test_rejects_conflicting_routes_with_no_spread_consensus():
    report = report_with_candidates((10.0, 10.2, 10.4, 10.6))

    row = select_boundary_consensus(report)["rows"][0]

    assert row["accepted"] is False
    assert row["target_time"] is None
    assert row["reason"] == "conflicting_candidates"
    assert row["evidence"]["combinations_within_spread"] == []


def test_rejects_unique_consensus_beyond_saved_boundary_shift_limit():
    report = report_with_candidates((10.6, 10.6, 10.6, 10.6))

    row = select_boundary_consensus(report)["rows"][0]

    assert row["accepted"] is False
    assert row["target_time"] is None
    assert row["reason"] == "shift_exceeds_limit"
    assert len(row["evidence"]["combinations_within_spread"]) == 1
    assert row["evidence"]["combinations_with_limits"] == []


def test_does_not_mutate_report_or_consult_lyric_marks():
    report = report_with_candidates()
    report["lyric_marks"] = [{"analysis_time": -1000, "reviewed": True}]
    before = deepcopy(report)

    result = select_boundary_consensus(report)

    assert report == before
    assert result["rows"][0]["target_time"] == pytest.approx(10.03)


def test_rejects_excessive_combination_count_without_enumerating():
    report = report_with_candidates()
    for source, method in ROUTES:
        boundary = report["sources"][source][method][0]["boundary"]
        boundary["persistent_crossing_clusters"] = [
            [time - 0.001, time + 0.001]
            for time in range(10, 19)
        ]

    row = select_boundary_consensus(report)["rows"][0]

    assert row["accepted"] is False
    assert row["target_time"] is None
    assert row["reason"] == "too_many_candidate_combinations"
    assert row["evidence"]["combination_count"] == 9 ** 4
