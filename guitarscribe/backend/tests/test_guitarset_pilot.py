import json

import numpy as np
import soundfile as sf

from scripts.benchmark_guitarset_pilot import merged, reference


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


def test_short_recording_is_diagnostic_not_quality_gate(tmp_path):
    audio = tmp_path / 'short_mic.wav'
    sf.write(audio, np.zeros(1000), 1000)
    jams = tmp_path / 'short.jams'
    jams.write_text(json.dumps({'file_metadata': {'duration': 1}, 'annotations': [
        {'namespace': 'chord', 'annotation_metadata': {'data_source': 'manual verification'},
         'data': [{'time': 0, 'duration': 1, 'value': 'C:maj'}]},
        {'namespace': 'tempo', 'data': [{'value': 120}]},
        {'namespace': 'beat_position', 'data': [
            {'time': 0, 'value': {'position': 1, 'measure': 1}},
            {'time': .5, 'value': {'position': 2, 'measure': 1}}]},
    ]}))
    annotation, _, _ = reference(jams, audio)
    assert annotation.evaluation_tier == 'smoke'
    assert annotation.excerpt_end == 1
