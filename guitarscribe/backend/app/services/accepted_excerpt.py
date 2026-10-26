"""Compose a separate excerpt from an accompaniment and saved melody.

Caller must verify that the accompaniment audio is the same source range.
No inference, timing quantization, persistence or mutation of either input.
"""
import math

from ..models.score import SongScore
from ..exporters.midi import compile_playback_manifest


def compose_excerpt(melody_source: SongScore, accompaniment: SongScore, start: float) -> SongScore:
    duration=accompaniment.song.duration_seconds
    if not all(math.isfinite(x) for x in [start,duration]) or not 0<=start<start+duration<=melody_source.song.duration_seconds:
        raise ValueError('Excerpt is outside saved melody timeline')
    if melody_source.key_context!=accompaniment.key_context or melody_source.guitar!=accompaniment.guitar or melody_source.analysis.capo!=accompaniment.analysis.capo:
        raise ValueError('Key, capo and guitar settings must match')
    if accompaniment.melody or accompaniment.lyrics or melody_source.lyrics or melody_source.melody_edits:
        raise ValueError('Requires accompaniment-only input and melody without lyrics/edit history; preserve these in original revision')
    if any(not math.isfinite(n.start+n.end) or n.end<=n.start for n in melody_source.melody):
        raise ValueError('Saved melody contains invalid timing')
    result=accompaniment.model_copy(deep=True)
    end=start+duration
    result.melody=[n.model_copy(update={'start':max(start,n.start)-start,'end':min(end,n.end)-start})
                   for n in melody_source.melody if n.start<end and n.end>start]
    result.song.source_start_seconds=melody_source.song.source_start_seconds+start
    result.provenance.melody_engine=melody_source.provenance.melody_engine
    result.provenance.melody_engine_version=melody_source.provenance.melody_engine_version
    for key,value in melody_source.provenance.parameters.items():
        if key.startswith(('melody_','bounded_','vocal_')):
            result.provenance.parameters[key]=value
    result.provenance.parameters['derived_excerpt']=True
    result.provenance.parameters['excerpt_parent_start']=start
    result.analysis.warnings.append('Separate excerpt: accompaniment retained from reviewed baseline; saved melody clipped only at excerpt edges, not corrected or re-transcribed. Original full revision is unchanged.')
    before=compile_playback_manifest(accompaniment)
    after=compile_playback_manifest(result)
    assert [e for e in before.events if e.track=='guitar']==[e for e in after.events if e.track=='guitar']
    return result
