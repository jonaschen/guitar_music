import pytest

from app.evaluation.external_reference import import_klangio_results
from app.evaluation.quality_report import evaluate_quality_layers
from app.evaluation.annotations import QualityAnnotation


def test_documented_results_keep_pickup_timing_and_unknown_distinct_from_silence():
    score = import_klangio_results(beats=[[.13, 4.0], [.61, 1.0], [1.12, 2.0]],
                                  chords=[[0, .3, "N"], [.3, 1.7, "C:min"], [1.7, 2, "X"]], duration=2)
    assert [b.time for b in score.beats] == [.13, .61, 1.12]
    assert [b.measure for b in score.beats] == [0, 1, 1]
    assert [c.symbol for c in score.chords] == ["N", "C:min", "X"]
    assert score.analysis.timing_status == "unmetered"  # import is not product approval


@pytest.mark.parametrize("beats", [[[0, 1], [0, 2]], [[-1, 1]], [[2, 1]], [[0, 1.5]],
                                  [[0, True]], [[float("nan"), 1]], [[.5, 2], [.2, 1]], {"beats": []}])
def test_reject_ambiguous_or_invalid_beat_payload(beats):
    with pytest.raises(ValueError):
        import_klangio_results(beats=beats, chords=None, duration=2)


@pytest.mark.parametrize("chords", [[], [[.2, 2, "C:maj"]], [[0, 1, "C:maj"]],
                                   [[0, 1.2, "N"], [1, 2, "C:maj"]], [[0, 3, "C:maj"]],
                                   [[0, 2, "not-a-chord"]]])
def test_reject_missing_coverage_instead_of_inventing_silence(chords):
    with pytest.raises(ValueError):
        import_klangio_results(beats=None, chords=chords, duration=2)


def test_independent_output_can_be_wrong_and_reference_scorer_exposes_it():
    ref = QualityAnnotation(recording_id="synthetic-contract", source_sha256="a"*64,
                            rights_note="test fixture", difficulty="easy", excerpt_start=0, excerpt_end=8,
                            beats=[{"time": i*.5} for i in range(16)],
                            downbeats=[{"time": i*2} for i in range(4)],
                            chords=[{"start": 0, "end": 8, "label": "C:maj"}])
    external = import_klangio_results(beats=[[i, (i%4)+1] for i in range(8)],
                                      chords=[[0, 8, "D:maj"]], duration=8)
    report = evaluate_quality_layers(external, ref)
    assert report["timing"]["beat_cml_total"] == 0
    assert report["chord"]["root_weighted_accuracy"] == 0


def test_unreported_bpm_is_not_scored_as_an_estimated_zero_tempo():
    ref = QualityAnnotation(recording_id="tempo", source_sha256="a"*64, rights_note="fixture",
                            difficulty="easy", excerpt_start=0, excerpt_end=2, tempo_bpm=120)
    score = import_klangio_results(beats=[], chords=None, duration=2)
    assert "bpm_relative_error" not in evaluate_quality_layers(score, ref)["timing"]
