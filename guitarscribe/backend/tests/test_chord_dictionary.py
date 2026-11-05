import pytest

from app.evaluation.chord_dictionary import DictionaryAvailability, cross_tabulate


def dictionary(*labels):
    return DictionaryAvailability([{"index": i, "label": label, "weights": [0]*24}
                                   for i, label in enumerate(labels)])


def test_root_alone_does_not_mean_reference_chord_is_available():
    assert dictionary("C").classify("C:dim7")["category"] == "candidate_pattern_absent"


def test_inversion_and_omission_are_distinct_from_strict_match():
    d = dictionary("C", "G")
    assert d.classify("C:maj")["category"] == "strict_label_match"
    assert d.classify("C:maj/3")["category"] == "missing_inversion_only"
    assert d.classify("C:maj(*5)")["category"] == "missing_omission_only"
    assert d.classify("C:maj(*5)/3")["category"] == "missing_omission_and_inversion"


def test_equal_pitch_set_with_other_root_is_not_strict_success():
    result = dictionary("Dm6").classify("B:hdim7/b3")
    assert result["category"] == "different_root_same_pitch_set_only"
    assert result["different_root_same_pitch_set"]


def test_omission_restoration_preserves_extensions_and_root():
    assert dictionary("C").classify("C:7(*5)")["category"] == "candidate_pattern_absent"
    assert dictionary("C7").classify("C:7(*5)")["category"] == "missing_omission_only"


def test_rootless_template_is_independent_of_label_and_bins_start_on_a():
    weights = [0]*24
    # C major without root: E (A-relative index 7), G (index 10).
    weights[12+7] = weights[12+10] = 1
    d = DictionaryAvailability([{"index": 0, "label": "C", "weights": weights}])
    result = d.classify("C:maj(*1)")
    assert result["category"] == "missing_omission_only"
    assert result["same_root_template_treble"]
    assert not d.classify("C:maj")["same_root_template_treble"]


def test_category_seconds_conserve_domain_and_wrong_root_is_a_subset():
    rows = [{"start": 0, "end": 4, "seconds": 4, "reference_label": "C", "estimate_label": "G", "category": "wrong_root"},
            {"start": 4, "end": 10, "seconds": 6, "reference_label": "C:maj/3", "estimate_label": "C", "category": "bass_only"}]
    result = cross_tabulate(rows, dictionary("C"))
    assert result["reference_seconds"] == 10
    assert result["wrong_root_seconds"] == 4
    assert result["categories"]["strict_label_match"]["wrong_root_fraction"] == 1
    assert result["categories"]["missing_inversion_only"]["reference_fraction"] == .6


def test_dictionary_rejects_incomplete_profiles():
    with pytest.raises(ValueError):
        DictionaryAvailability([{"index": 0, "label": "C", "weights": [1]*12}])
