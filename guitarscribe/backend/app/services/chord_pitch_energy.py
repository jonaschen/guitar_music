"""Bounded source-audio energy observations, never chord or note predictions."""
import math
import numpy as np
from scipy.signal import resample_poly


def pitch_energy(audio, rate):
    signal=np.asarray(audio,dtype=np.float64)
    if not isinstance(rate,(int,float)) or not math.isfinite(rate) or rate<8000 or signal.ndim not in (1,2):raise ValueError('Invalid audio')
    if signal.ndim==1:signal=signal[:,None]
    if signal.shape[1] not in (1,2) or not .5<=len(signal)/rate<=30.001 or not np.isfinite(signal).all():raise ValueError('Use 0.5–30 seconds of mono/stereo audio')
    rate=int(rate);target=22050
    if rate!=target:
        divisor=math.gcd(rate,target);signal=resample_poly(signal,target//divisor,rate//divisor,axis=0)
    rms=float(np.sqrt(np.mean(signal**2)));rms_db=20*math.log10(max(rms,1e-12))
    result=dict(method='stft-pitch-class-energy-v1',interpretation='energy_not_notes_or_chord_members',
        rate=target,fft_size=8192,hop=2048,frequency_range_hz=[65.406,2093.005],rms_db=rms_db)
    if rms_db < -90:return dict(**result,state='insufficient',pitch_classes=[])
    size=8192;window=np.hanning(size);power=np.zeros(size//2+1);count=0
    # Never include samples outside the requested interval. Padding does not add resolution.
    padded=np.pad(signal,((size//2,size//2),(0,0)))
    for start in range(0,len(signal),2048):
        frame=padded[start:start+size]*window[:,None]
        power+=np.mean(abs(np.fft.rfft(frame,axis=0))**2,axis=1)/(window.sum()**2);count+=1
    power/=count
    frequency=np.fft.rfftfreq(size,1/target);mask=(frequency>=65.406)&(frequency<=2093.005)
    midi=np.rint(69+12*np.log2(frequency[mask]/440)).astype(int)
    energy=np.bincount(midi%12,weights=power[mask],minlength=12)
    if energy.max()<1e-14:return dict(**result,state='insufficient',pitch_classes=[])
    db=10*np.log10(np.maximum(energy,1e-20));relative=np.maximum(-100,db-db.max())
    return dict(**result,state='available',pitch_classes=[dict(pitch_class=i,relative_db=float(relative[i])) for i in range(12)])
