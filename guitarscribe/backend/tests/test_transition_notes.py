import math
import numpy as np
import pytest
from app.models.analysis import MelodyNote
from app.models.melody_contour import MelodyContour
from app.evaluation.transition_notes import repair_transitions, detect_attacks
from app.evaluation.source_timed_audit import connected_note_frames, frame_loss


def fixture(pitches=(60,62,64), durations=(4,1,4), confidence=(.9,.2,.9)):
    hop=.02;notes=[];hz=[];probs=[];frame=0
    for i,(pitch,duration,p) in enumerate(zip(pitches,durations,confidence)):
        notes.append(MelodyNote(id=str(i),start=frame*hop,end=(frame+duration)*hop,midi=pitch,note='C4',confidence=p))
        hz += [440*2**((pitch-69)/12)]*duration;probs += [p]*duration;frame+=duration
    c=MelodyContour(source_artifact_sha256='a'*64,source_start=0,source_end=frame*hop,hop_seconds=hop,frequencies_hz=hz,voiced_probabilities=probs)
    return notes,c


def test_bridge_moves_one_boundary_without_losing_voicing_or_mutating_baseline():
    notes,c=fixture();before=[n.model_dump() for n in notes]
    result,changes=repair_transitions(notes,c,[])
    assert len(result)==2 and len(changes)==1
    assert result[0].start==notes[0].start and result[-1].end==notes[-1].end
    assert result[0].end==result[1].start
    assert [n.model_dump() for n in notes]==before
    loss=frame_loss(connected_note_frames(notes,c),connected_note_frames(result,c),c.hop_seconds,0,c.source_end)
    assert loss['dropped']==loss['invented_voicing']==0
    assert loss['changed_pitch']==1


@pytest.mark.parametrize('pitches,durations,confidence',[
    ((60,62,64),(4,3,4),(.9,.2,.9)), # distinct stable middle plateau
    ((60,62,64),(4,1,4),(.9,.9,.9)), # reliable fast note
    ((60,62,60),(4,1,4),(.9,.2,.9)), # ornament / non-monotone excursion
    ((60,62,64),(2,1,4),(.9,.2,.9)), # no stable left anchor
    ((60,62,64,65,67),(4,2,2,2,4),(.9,.2,.2,.2,.9)), # long fast run
])
def test_controls_are_preserved(pitches,durations,confidence):
    notes,c=fixture(pitches,durations,confidence)
    result,changes=repair_transitions(notes,c,[])
    assert result==notes and changes==[]


def test_audio_attack_veto_preserves_short_note():
    notes,c=fixture()
    assert repair_transitions(notes,c,[notes[1].start])==(notes,[])


def test_positive_gap_is_never_filled_even_below_one_frame():
    notes,c=fixture();notes[1].start+=1e-8
    assert repair_transitions(notes,c,[])==(notes,[])


def test_unvoiced_contour_inside_candidate_bridge_rejects_it():
    notes,c=fixture();values=list(c.frequencies_hz);values[4]=None
    c=c.model_copy(update={'frequencies_hz':tuple(values)})
    assert repair_transitions(notes,c,[])==(notes,[])


def test_descending_chain_and_shared_anchor_preserve_order():
    notes,c=fixture((72,71,70,68,65,64,66,67),(4,1,1,1,1,4,1,4),(.9,.1,.1,.1,.1,.9,.1,.9))
    result,changes=repair_transitions(notes,c,[])
    assert len(changes)==2 and [n.midi for n in result]==[72,64,67]
    assert all(a.end==b.start for a,b in zip(result,result[1:]))
    assert all(n.end>n.start for n in result)


def test_audio_veto_detects_a_new_attack_and_ignores_silence():
    sr=22050;t=np.arange(sr)/sr
    audio=.2*np.sin(2*math.pi*440*t)*((t>.1)&(t<.4))
    audio+=.3*np.sin(2*math.pi*660*t)*(t>.6)
    times=detect_attacks(audio,sr,.02)
    assert any(abs(t-.6)<.05 for t in times)
    assert detect_attacks(np.zeros(sr),sr,.02)==[]


def test_packet_keeps_sources_unchanged_and_refuses_wrong_or_edited_g(tmp_path):
    import soundfile as sf
    from app.models.score import SongScore, SongInfo
    from app.models.analysis import BeatInfo
    from app.evaluation.bounded_checkpoint import build_score
    from app.evaluation.transition_checkpoint import packet
    _,contour=fixture()
    score=build_score(SongScore(song=SongInfo(duration_seconds=contour.source_end)),contour)
    score.beats=[BeatInfo(time=.005*i,measure=i+1,beat=1,confidence=1) for i in range(36)]
    job=tmp_path/'job';job.mkdir()
    score.provenance.parameters['candidate_source_job_id']='job'
    (job/'melody-contour.json').write_text(contour.model_dump_json())
    audio=np.sin(np.arange(round(contour.source_end*22050))*2*np.pi*440/22050)*.2
    for name in ('vocal-stem.wav','analysis-source.wav'):sf.write(job/name,audio,22050)
    saved=tmp_path/'saved.json';saved.write_text(score.model_dump_json())
    originals={p:p.read_bytes() for p in [saved,*job.iterdir()]}
    output=tmp_path/'new'
    report=packet(job,saved,output)
    assert report['full_loss']['dropped']==report['full_loss']['invented_voicing']==0
    assert (output/'index.html').exists()
    assert all(p.read_bytes()==data for p,data in originals.items())
    with pytest.raises(FileExistsError):packet(job,saved,output)
    score.melody[0].edited=True;saved.write_text(score.model_dump_json())
    with pytest.raises(ValueError,match='unedited'):packet(job,saved,tmp_path/'bad')
    score.melody[0].edited=False;score.melody[0].midi+=1;saved.write_text(score.model_dump_json())
    with pytest.raises(ValueError,match='does not match'):packet(job,saved,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_fractional_sample_hop_attack_remains_aligned():
    sr=1000;hop=.0232;t=np.arange(sr*10)/sr
    audio=.2*np.sin(2*np.pi*120*t)*(t>9)
    assert any(abs(t-9)<.05 for t in detect_attacks(audio,sr,hop))
