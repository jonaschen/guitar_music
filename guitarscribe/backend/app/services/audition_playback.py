"""Playback-only chord/root and observed-pulse controls. Never mutates the score."""
import hashlib
import json
import math
import re
from bisect import bisect_right

from ..exporters.midi import PlaybackEvent,compile_playback_manifest,_selected_voicing_pitches,_strum_profile
from .playable_chords import with_default_voicings
from .downbeat_rhythm import downbeat_events,NO_CHORD
from .transposition import NOTE_TO_PITCH


def root_pitch(symbol):
    match=re.match(r'^([A-G](?:#|b)?)(?=[:/a-zA-Z0-9(#*+\-]|$)',symbol.strip().replace('♯','#').replace('♭','b'))
    if not match or match[1] not in NOTE_TO_PITCH:raise ValueError('無法辨識和弦根音：'+symbol)
    # Sounding symbol already includes transposition; capo must not be added again.
    pc=NOTE_TO_PITCH[match[1]]
    return 40+(pc-4)%12


def observed_units(score,preview=None):
    duration=score.song.duration_seconds
    if score.analysis.timing_status!='unmetered':
        downbeat_events(score)  # existing finite/ordered/numbered grid and chord guards
        meter=int(score.analysis.time_signature[0]);beats=score.beats
        return [(b.time,beats[i+1].time if i+1<len(beats) else duration,b.beat,
                 (b.measure-1)*meter+b.beat-1,duration,i+1<len(beats))
                for i,b in enumerate(beats) if b.time<duration]
    if not preview or preview.get('duration_seconds')!=duration or preview.get('source_start_seconds')!=score.song.source_start_seconds:
        raise ValueError('沒有相符的局部拍點可供試聽。')
    units=[];cursor=0.
    for region in preview.get('regions',[]):
        start,end=region['start'],region['end'];meter=region['beats_per_bar']
        if not all(math.isfinite(v) for v in (start,end)) or not 0<=cursor<=start<end<=duration or meter not in (3,4):
            raise ValueError('局部拍點範圍無效。')
        cursor=start
        for bar_index,bar in enumerate(region['bars']):
            times=bar['beats']
            if len(times)!=meter+1 or times[0]!=cursor or times[0]!=bar['start'] or times[-1]!=bar['end'] or not bar['end']<=end:
                raise ValueError('局部小節邊界無效。')
            if any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
                raise ValueError('局部拍點未按時間排列。')
            for i in range(meter):units.append((times[i],times[i+1],i+1,bar_index*meter+i,end,True))
            cursor=bar['end']
        if cursor!=end:raise ValueError('局部小節未覆蓋區段。')
    if not units:raise ValueError('沒有可供試聽的拍點；請沿用原刷奏。')
    return units


def audition_manifest(score,content='chord',pulse='original',preview=None):
    if content not in ('chord','root') or pulse not in ('original','bar','two','one','half'):
        raise ValueError('無效的試聽選項。')
    base=compile_playback_manifest(score)
    if content=='chord' and pulse=='original':return base
    chords=score.chords;by_id={c.id:c for c in chords}
    if pulse=='original':
        events=[]
        for event in base.events:
            if event.track=='guitar':
                chord=by_id.get(event.source_id)
                if chord is None:raise ValueError('演奏事件缺少對應和弦。')
                event=event.model_copy(update=dict(pitches=(root_pitch(chord.symbol),),pitch_offsets=(0.,),pitch_velocities=(event.velocity,)))
            events.append(event)
    else:
        units=observed_units(score,preview)
        if any(not math.isfinite(c.start+c.end) or not 0<=c.start<c.end<=score.song.duration_seconds for c in chords) or any(a.end>b.start for a,b in zip(chords,chords[1:])) or len(by_id)!=len(chords):
            raise ValueError('和弦時間或編號無效。')
        resolved=with_default_voicings(score)
        pitches=[() if c.symbol.strip().lower() in NO_CHORD else
                 (root_pitch(c.symbol),) if content=='root' else _selected_voicing_pitches(resolved,c)
                 for c in resolved.chords]
        ring=[c.end for c in chords]
        for i in range(len(chords)-2,-1,-1):
            if pitches[i] and pitches[i+1] and abs(chords[i].end-chords[i+1].start)<1e-9:ring[i]=ring[i+1]
        attacks=[]
        for start,end,beat,ordinal,limit,has_next in units:
            if pulse=='bar' and beat!=1 or pulse=='two' and ordinal%2:continue
            attacks.append((start,beat,limit))
            if pulse=='half' and has_next:attacks.append(((start+end)/2,0,limit))
        events=[e for e in base.events if e.track!='guitar'];starts=[c.start for c in chords]
        for i,(start,beat,limit) in enumerate(attacks):
            index=bisect_right(starts,start)-1
            if index<0 or not start<chords[index].end or not pitches[index]:continue
            end=min(ring[index],limit,attacks[i+1][0] if i+1<len(attacks) else score.song.duration_seconds)
            if end<=start:continue
            offsets,velocities=_strum_profile('D',len(pitches[index]),min(.06,(end-start)/2))
            if beat!=1:velocities=tuple(max(1,round(v*.7)) for v in velocities)
            events.append(PlaybackEvent(id=f'audition:{pulse}:{i}',track='guitar',start=start,end=end,sustain_end=end,
                pitches=pitches[index],pitch_offsets=offsets,pitch_velocities=velocities,velocity=velocities[0],stroke='D',source_id=chords[index].id))
    events.sort(key=lambda e:(e.start,e.track,e.id))
    revision=hashlib.sha256(json.dumps(dict(base=base.revision,content=content,pulse=pulse,
        events=[e.model_dump(mode='json') for e in events]),sort_keys=True).encode()).hexdigest()[:16]
    return base.model_copy(update=dict(revision=revision,events=tuple(events)))
