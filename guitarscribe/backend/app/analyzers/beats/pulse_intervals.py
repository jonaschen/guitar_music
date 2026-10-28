"""Descriptive pulse diagnostics, not a musical validity gate or beat repair."""
from math import isfinite
from statistics import median


def describe_pulse_intervals(beats):
    if len(beats)<3 or any(not isinstance(t,(int,float)) or isinstance(t,bool) or not isfinite(t) for t in beats):
        return dict(median_seconds=None, deviations=[])
    intervals=[b-a for a,b in zip(beats,beats[1:])]
    if any(value<=0 for value in intervals):
        return dict(median_seconds=None, deviations=[])
    baseline=median(intervals)
    # Ratios report pulse density only. Real pauses/tempo changes remain possible.
    deviations=[dict(start=a,end=b,seconds=b-a,ratio_to_median=(b-a)/baseline,
                     kind='long_interval' if (b-a)/baseline>=1.75 else 'short_interval')
                for a,b in zip(beats,beats[1:]) if (b-a)/baseline>=1.75 or (b-a)/baseline<=.6]
    return dict(median_seconds=baseline,deviations=deviations)
