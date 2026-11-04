"""One fixed, data-derived tempo band for a separately labelled candidate.

No song-specific inputs. This is not proof that the dominant pulse is the
musical quarter note; it deliberately declines mixed/variable tempo evidence.
"""
import math

POLICY = 'duration-majority-tempo-v1'
BAND = .15
MIN_SUPPORT = .75


def tempo_reference(beats):
    report = dict(policy=POLICY, eligible=False, band_fraction=BAND, minimum_support=MIN_SUPPORT)
    if len(beats)<17 or any(not isinstance(t,(int,float)) or isinstance(t,bool) or not math.isfinite(t) or t<0 for t in beats):
        return {**report,'reason':'insufficient_valid_observations'}
    intervals=[b-a for a,b in zip(beats,beats[1:])]
    if any(t<=0 for t in intervals):
        return {**report,'reason':'unordered_observations'}
    total=sum(intervals);cumulative=0
    for period in sorted(intervals):
        cumulative+=period
        if cumulative>=total/2:
            center=period;break
    supported=[t for t in intervals if center*(1-BAND)<=t<=center*(1+BAND)]
    support=sum(supported)/total
    # Keep the weighted-median centre, not a new per-song fitted window.
    low=max(55.,60/(center*(1+BAND)));high=min(215.,60/(center*(1-BAND)))
    report.update(period_seconds=center,support_fraction=support,observed_seconds=total,
                  min_bpm=low,max_bpm=high)
    if support<MIN_SUPPORT or len(supported)<16:
        return {**report,'reason':'no_dominant_tempo'}
    if low>=high:
        return {**report,'reason':'outside_decoder_range'}
    return {**report,'eligible':True,'reason':'dominant_tempo_candidate'}


def decode_continuity(beat_logits, downbeat_logits, reference):
    if not reference['eligible']:
        raise ValueError('No dominant tempo reference')
    from beat_this.model.postprocessor import Postprocessor
    from madmom.features.downbeats import DBNDownBeatTrackingProcessor
    decoder=Postprocessor('dbn')
    decoder.dbn=DBNDownBeatTrackingProcessor(beats_per_bar=[3,4],fps=50,
        min_bpm=reference['min_bpm'],max_bpm=reference['max_bpm'],transition_lambda=100)
    return tuple([float(t) for t in values] for values in decoder(beat_logits,downbeat_logits))
