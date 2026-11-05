import pytest
from scripts.evaluate_ismir2019_candidate import parse_lab


def test_original_harmony_and_explicit_silence_survive_clipping():
    events=parse_lab('0 1 N\n1 4 C:7/3\n4 6 D:min9\n',5)
    assert [e.symbol for e in events]==['N','C:7/3','D:min9']
    assert events[-1].end==5


@pytest.mark.parametrize('lab',['0 2 C:maj\n1 3 D:maj','0 inf C:maj','0 1 rubbish',''])
def test_invalid_or_unmapped_labs_fail_instead_of_becoming_triads(lab):
    with pytest.raises(Exception):parse_lab(lab,5)
