"""Full-song adapter must preserve labels and clip without shifting time."""
import copy
import pytest
from scripts.benchmark_mirex_mixed import annotation


def metadata():
    return dict(id='fixture',title='Synthetic',artist='Test',source='https://example.org/test',
        license='CC BY-NC 4.0',audio_offset=0,reference=[[0.,2.,'A:maj7(#9,13)'],[2.,4.01,'C#:min/b3']],downbeats=[.03,2.,4.01])


def test_decoded_end_clips_reference_but_keeps_extended_labels_and_unknown_meter(tmp_path):
    source=tmp_path/'synthetic.wav';source.write_bytes(b'synthetic source identity')
    data=metadata();saved=copy.deepcopy(data)
    a=annotation(data,source,4.)
    assert a.excerpt_start==0 and a.excerpt_end==4.
    assert a.chords[0].label=='A:maj7(#9,13)' and a.chords[1].label=='C#:min/b3'
    assert a.chords[1].end==4. and a.chords[1].start==2.
    assert [x.time for x in a.downbeats]==[.03,2.]
    assert a.meter=='' and a.beats==[] and a.tempo_bpm is None
    assert a.evaluation_tier=='smoke' and data==saved


@pytest.mark.parametrize('problem',['offset','gap','overlap','invalid_label','license','nonfinite'])
def test_cannot_silently_repair_or_drop_invalid_reference(tmp_path,problem):
    source=tmp_path/'synthetic.wav';source.write_bytes(b'synthetic')
    d=metadata()
    if problem=='offset':d['audio_offset']=.1
    elif problem=='gap':d['reference'][1][0]=2.1
    elif problem=='overlap':d['reference'][1][0]=1.9
    elif problem=='invalid_label':d['reference'][1][2]='not-a-chord'
    elif problem=='license':d['license']='unknown'
    elif problem=='nonfinite':d['reference'][1][1]=float('nan')
    with pytest.raises(ValueError):annotation(d,source,4.)
