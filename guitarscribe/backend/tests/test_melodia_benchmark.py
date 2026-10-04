import pytest
from app.evaluation.melodia_benchmark import validate_pitch


def test_preserves_unvoiced_and_fractional_pitch_without_confidence_promotion():
    assert validate_pitch([440.12,0,550,660],[.8,.9,0,-.1]) == [440.12,None,None,None]


@pytest.mark.parametrize("pitch,confidence", [([],[]),([440],[]),([float("nan")],[.5]),
    ([440],[float("inf")]),([8000],[.5])])
def test_rejects_invalid_engine_outputs(pitch,confidence):
    with pytest.raises(ValueError):
        validate_pitch(pitch,confidence)
