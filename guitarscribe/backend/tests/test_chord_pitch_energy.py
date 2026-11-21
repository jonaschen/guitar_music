import numpy as np
import pytest
from app.services.chord_pitch_energy import pitch_energy


def samples(notes,rate=22050,seconds=2):
    t=np.arange(int(rate*seconds))/rate
    return sum(.1*np.sin(2*np.pi*440*2**((m-69)/12)*t) for m in notes)


def test_pitch_energy_separates_major_minor_without_claiming_chord_detection():
    major=pitch_energy(samples([55,59,62]),22050);minor=pitch_energy(samples([55,58,62]),22050)
    assert major['state']=='available' and major['method']=='stft-pitch-class-energy-v1'
    assert major['pitch_classes'][11]['relative_db']>major['pitch_classes'][10]['relative_db']+8
    assert minor['pitch_classes'][10]['relative_db']>minor['pitch_classes'][11]['relative_db']+8
    assert 'chord' not in major and 'confidence' not in major


def test_silence_is_insufficient_and_antiphase_stereo_does_not_cancel():
    assert pitch_energy(np.zeros(22050),22050)['state']=='insufficient'
    mono=samples([57]);stereo=np.column_stack([mono,-mono]);result=pitch_energy(stereo,22050)
    assert max(result['pitch_classes'],key=lambda r:r['relative_db'])['pitch_class']==9
    assert result['rms_db']==pytest.approx(pitch_energy(mono,22050)['rms_db'])


def test_melody_and_harmonics_remain_energy_not_extra_chord_members():
    result=pitch_energy(samples([48,52,55,71]),22050)
    assert result['pitch_classes'][11]['relative_db']>-12
    assert result['interpretation']=='energy_not_notes_or_chord_members'
    assert all(np.isfinite(r['relative_db']) and r['relative_db']<=0 for r in result['pitch_classes'])


@pytest.mark.parametrize('audio,rate',[(np.zeros(100),22050),(np.full(22050,np.nan),22050),(np.zeros((22050,3)),22050),(np.zeros(22050),0)])
def test_invalid_or_too_short_audio_is_rejected(audio,rate):
    with pytest.raises(ValueError):pitch_energy(audio,rate)
