"""Independent small controls for the diagnostic, not musical accuracy tests."""
import copy
from scripts.count_melody_grid_conflicts import count, grid_points, raw_some


def test_variable_beats_and_earlier_midpoint_tie():
    points = grid_points([0, 1, 3], 4)
    assert points == [0, .25, .5, .75, 1, 1.5, 2, 2.5, 3]
    notes = [dict(start=.125, end=.2, midi=60), dict(start=1.25, end=1.4, midi=62)]
    r = count(notes, points, 3)
    assert [n['mapped_start'] for n in r['mapping']] == [0, 1]
    assert r['collision_groups'] == 0


def test_triple_collision_counts_all_notes_without_merging_same_pitch():
    notes = [dict(start=t, end=t+.01, midi=p) for t,p in [(.01,60),(.02,60),(.03,62),(.51,64)]]
    original = copy.deepcopy(notes)
    r = count(notes, grid_points([0,1],4), 1)
    assert (r['collision_groups'],r['involved_notes'],r['excess_occupants']) == (1,3,2)
    assert r['adjacent_collision_pairs']==2 and r['same_pitch_adjacent_collision_pairs']==1
    assert not r['onset_collision_gate_passed']
    assert notes==original and len(r['mapping'])==4 and r['deletions']==r['merges']==0


def test_raw_rest_time_and_chunk_offset_are_preserved():
    notes = raw_some([dict(offset=2,note_dur=[.25,.5,.25],note_rest=[False,True,False],note_midi=[60.1,0,60.2])])
    assert [(n['start'],n['end'],n['midi']) for n in notes]==[(2,2.25,60),(2.75,3,60)]
    assert [n['raw_event'] for n in notes]==[0,2]


def test_outside_coverage_is_not_clamped_and_boundary_is_reported():
    notes=[dict(start=t,end=t+.01,midi=60) for t in [-.2,.01,.99]]
    r=count(notes,grid_points([0,1],4),1)
    assert len(r['uncovered_onsets'])==1
    assert len(r['outside_clip_mappings'])==1
    assert r['outside_clip_mappings'][0]['mapped_start']==1
    assert not r['onset_collision_gate_passed']
