import numpy as np
import pytest

from app.evaluation.onset_notes import decode_onset_aware
from app.models.melody_contour import MelodyContour

RATE = 22050


def contour(pitches, hop=.005, offset=0):
    return MelodyContour(source_artifact_sha256="0"*64, source_start=offset,
                         source_end=offset+len(pitches)*hop, hop_seconds=hop,
                         frequencies_hz=[None if p is None else 440*2**((p-69)/12) for p in pitches],
                         voiced_probabilities=[0 if p is None else 1 for p in pitches])


def wave(events, duration=1):
    audio = np.zeros(round(duration*RATE))
    for start,end,midi in events:
        a,b=round(start*RATE),round(end*RATE)
        tone=.2*np.sin(2*np.pi*440*2**((midi-69)/12)*np.arange(b-a)/RATE)
        edge=min(round(.005*RATE),len(tone)//2)
        if edge:
            tone[:edge]*=np.linspace(0,1,edge)
            tone[-edge:]*=np.linspace(1,0,edge)
        audio[a:b]+=tone
    return audio


def test_audio_restores_touching_same_pitch_without_reference_input_or_mutation():
    c=contour([60]*200)
    audio=wave([(0,.5,60),(.5,1,60)])
    saved=c.model_dump_json(); copied=audio.copy()
    notes=decode_onset_aware(c,audio,RATE)
    assert len(notes)==2
    assert notes[0].end == pytest.approx(.5,abs=.004)
    assert notes[0].end==notes[1].start
    assert [(n.midi,n.start if i==0 else n.end) for i,n in enumerate(notes)]==[(60,0),(60,1)]
    assert c.model_dump_json()==saved
    assert np.array_equal(audio,copied)


def test_75ms_note_rests_and_sustained_note_are_not_globally_removed():
    pitches=[None]*20+[65]*15+[None]*25+[69]*140
    c=contour(pitches)
    notes=decode_onset_aware(c,wave([(.1,.175,65),(.3,1,69)]),RATE)
    assert [(n.start,n.end,n.midi) for n in notes]==[(.1,.17500000000000002,65),(.3,1,69)]


def test_constant_amplitude_vibrato_does_not_invent_reattacks():
    t=np.arange(RATE)/RATE
    hz=440*2**((.15*np.sin(2*np.pi*6*t))/12)
    audio=.2*np.sin(2*np.pi*np.cumsum(hz)/RATE)
    notes=decode_onset_aware(contour([69]*200),audio,RATE)
    assert len(notes)==1
    assert (notes[0].start,notes[0].end,notes[0].midi)==(0,1,69)


def test_only_onset_supported_monotone_two_frame_bridge_is_reassigned():
    c=contour([60]*48+[62]*2+[64]*50,hop=.01)
    notes=decode_onset_aware(c,wave([(0,.5,60),(.5,1,64)]),RATE)
    assert [n.midi for n in notes]==[60,64]
    assert notes[0].end==notes[1].start==pytest.approx(.5,abs=.004)


def test_no_audio_attack_preserves_short_pitch_and_late_outer_endpoint():
    c=contour([60]*48+[62]*2+[64]*50,hop=.01,offset=2)
    t=np.arange(RATE)/RATE
    audio=.2*np.sin(2*np.pi*440*t)
    notes=decode_onset_aware(c,audio,RATE)
    assert [n.midi for n in notes]==[60,62,64]
    assert notes[0].start==2 and notes[-1].end==3


def test_invalid_audio_is_rejected_and_silence_does_not_fill_contour_rests():
    c=contour([None]*200)
    assert decode_onset_aware(c,np.zeros(RATE),RATE)==[]
    with pytest.raises(ValueError):decode_onset_aware(c,np.zeros(10),RATE)
    with pytest.raises(ValueError):decode_onset_aware(c,np.full(RATE,np.nan),RATE)


def test_clear_silence_shrinks_smeared_short_note_within_known_window():
    c=contour([None]*70+[65]*65+[None]*265,hop=.0025)
    notes=decode_onset_aware(c,wave([(.2,.275,65)]),RATE)
    assert len(notes)==1 and notes[0].midi==65
    assert notes[0].start==pytest.approx(.2,abs=.008)
    assert notes[0].end==pytest.approx(.275,abs=.008)
    assert .175 <= notes[0].start < notes[0].end <= .3375


def test_audio_edges_outside_window_do_not_erase_or_extend_notes():
    c=contour([60]*200)
    notes=decode_onset_aware(c,wave([(.2,.8,60)]),RATE)
    assert len(notes)==1
    assert notes[0].start==0 and notes[0].end==1
