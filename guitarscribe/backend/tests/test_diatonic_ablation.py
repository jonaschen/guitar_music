from pathlib import Path
import struct
import subprocess
import numpy as np
import pytest
from scripts.run_diatonic_ablation import profile_mask,scales,raw_events


def profile(index,label,pitches):
    weights=[0.]*24
    for pc in pitches:weights[12+(pc-9)%12]=1.
    return dict(index=index,label=label,weights=weights)


def test_a_bin_mapping_and_bass_tones_are_both_used():
    entries=[profile(0,'C',[0,4,7]),profile(1,'C',[0,4,7]),profile(2,'N',[])]
    entries[1]['weights'][(1-9)%12]=.5
    assert profile_mask(entries,'C','major').tolist()==[True,False,True]


def test_minor_requires_one_complete_scale_not_union_of_eight_tones():
    entries=[profile(0,'Am7',[9,0,4,7]),profile(1,'AmMaj7',[9,0,4,8]),profile(2,'mixed',[9,0,4,7,8]),profile(3,'N',[])]
    assert profile_mask(entries,'A','minor').tolist()==[True,True,False,True]
    assert len(scales('A','minor'))==2 and all(len(s)==7 for s in scales('A','minor'))


def test_empty_non_n_is_not_eligible_and_indices_must_stay_contiguous():
    entries=[profile(0,'C',[]),profile(1,'N',[])]
    assert profile_mask(entries,'C','major').tolist()==[False,True]
    entries[0]['index']=5
    with pytest.raises(ValueError):profile_mask(entries,'C','major')


def test_raw_events_keep_same_named_profile_changes_and_terminal_n():
    trace=dict(dictionary=[profile(0,'C',[0,4,7]),profile(1,'C',[0,4,7]),profile(2,'N',[])],
               frames=[dict(sec=0,nsec=200000000),dict(sec=0,nsec=300000000),dict(sec=0,nsec=400000000)])
    events=raw_events(trace,[2,0,1])
    assert [e['label'] for e in events]==['N','C','C','N']
    assert [e['timestamp'] for e in events]==pytest.approx([.2,.3,.4,.4])


def test_original_cpp_tie_order_and_mask_never_select_excluded_state(tmp_path):
    source=Path('/home/jonas/.cache/guitarscribe-chordino-diagnostic/source')
    if not (source/'viterbi.cpp').exists():pytest.skip('Original author source not installed')
    wrapper=Path(__file__).resolve().parents[1]/'scripts/replay_chord_viterbi.cpp';binary=tmp_path/'decoder'
    subprocess.run(['g++','-O2','-std=c++17','-I',str(source),str(wrapper),str(source/'viterbi.cpp'),'-o',str(binary)],check=True)
    values=np.array([[.1,.1,.8],[.5-5e-10,.5-5e-10,1e-9],[.5-5e-10,.5-5e-10,1e-9]],dtype='<f8')
    paths=[]
    for masked in [False,True]:
        matrix=values.copy()
        if masked:matrix[:,0]=0
        inp=tmp_path/('mask' if masked else 'base');out=inp.with_suffix('.path')
        inp.write_bytes(struct.pack('<QQ',*matrix.shape)+matrix.tobytes())
        subprocess.run([str(binary),str(inp),str(out)],check=True)
        paths.append(np.fromfile(out,dtype='<i4').tolist())
    assert paths==[[2,0,0],[2,1,1]]
