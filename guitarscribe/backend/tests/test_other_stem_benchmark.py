import numpy as np
import pytest
from app.evaluation.other_stem_benchmark import source_variants


def test_control_excludes_vocals_and_other_excludes_drums_bass_without_mutation():
    stems={name:np.full((10,2),value,dtype=float) for name,value in
           [("vocals",100),("drums",1),("bass",2),("other",4)]}
    result=source_variants(stems)
    assert np.all(result["N-local-accompaniment"]==7)
    assert np.all(result["O-other"]==4)
    result["O-other"][:]=0
    assert np.all(stems["other"]==4)


def test_rejects_missing_stems_or_mismatched_shapes():
    with pytest.raises(ValueError,match="four"):
        source_variants({"other":np.zeros((10,2))})
    stems={name:np.zeros((10,2)) for name in ["vocals","drums","bass","other"]}
    stems["other"]=np.zeros((9,2))
    with pytest.raises(ValueError,match="shapes"):
        source_variants(stems)
