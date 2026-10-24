from types import SimpleNamespace

import pytest

from app.evaluation.chord_evidence import root_evidence_report


def chord(start, end, label):
    return SimpleNamespace(start=start, end=end, label=label)


def test_root_rank_counts_distinct_roots_and_weights_actual_overlap():
    result = root_evidence_report(
        [(0, 2, [.9, .8, .7]), (2, 3, [.1, .2, .9])],
        ['G#', 'Abm', 'C#'], [chord(0, 3, 'Ab:min7')])
    assert result['top1_root_duration_fraction'] == pytest.approx(2 / 3)
    assert result['top3_root_duration_fraction'] == 1
    assert [row['reference_root_rank'] for row in result['overlaps']] == [1, 2]


def test_tied_roots_do_not_claim_unambiguous_top1():
    result = root_evidence_report([(0, 1, [.5, .5])], ['C', 'G'], [chord(0, 1, 'C:maj')])
    assert result['top1_root_duration_fraction'] == 0
    assert result['overlaps'][0]['reference_root_rank'] == 2


def test_unpitched_and_absent_roots_are_not_counted_correct():
    result = root_evidence_report([(0, 3, [.9])], ['C'],
                                  [chord(0, 1, 'N'), chord(1, 3, 'G:maj')])
    assert result['pitched_overlap_seconds'] == 2
    assert result['unpitched_overlap_seconds'] == 1
    assert result['top3_root_duration_fraction'] == 0
    assert result['overlaps'][0]['reference_root_rank'] is None
