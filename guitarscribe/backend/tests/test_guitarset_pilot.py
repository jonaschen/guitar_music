from scripts.benchmark_guitarset_pilot import merged


def test_merges_adjacent_harmony_ignoring_inversion_without_losing_seventh():
    result=merged([
        {'start':0,'end':1,'label':'C:maj/3'},
        {'start':1,'end':2,'label':'C:maj/5'},
        {'start':2,'end':3,'label':'C:7'},
    ],0,3,'label')
    assert result==[{'start':0,'end':2,'label':'C:maj'}, {'start':2,'end':3,'label':'C:7'}]


def test_never_merges_across_an_unannotated_gap():
    result=merged([{'start':0,'end':1,'label':'G'}, {'start':2,'end':4,'label':'G'}],.5,3,'label')
    assert result==[{'start':.5,'end':1,'label':'G:maj'}, {'start':2,'end':3,'label':'G:maj'}]
