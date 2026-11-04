import pytest
from app.models.score import SongScore,SongInfo,AnalysisSummary
from app.models.analysis import ChordEvent
from app.services.timing_checkpoint_candidate import build_checkpoint_candidate


def inputs():
    s=SongScore(song=SongInfo(duration_seconds=10,source_url='https://example.test/song'),
        analysis=AnalysisSummary(timing_status='unmetered',bpm=0,time_signature=''),
        chords=[ChordEvent(id='c',symbol='C',start=.19,end=9.7,edited=True)])
    r=dict(case=dict(duration=10,source_url=s.song.source_url,job='original',source_sha256='hash'),
        checkpoint='final0',weights_sha256='weights',beat_this='test',
        decoders=dict(dbn=dict(beats=[i*.5 for i in range(20)],downbeats=[0,2,4,6,8])))
    return s,r


def test_candidate_only_changes_timing_with_explicit_unconfirmed_provenance():
    s,r=inputs();before=s.model_dump_json();c=build_checkpoint_candidate(s,r)
    assert s.model_dump_json()==before
    assert c.chords==s.chords and c.rhythm==s.rhythm and c.guitar==s.guitar
    assert c.analysis.timing_status=='metered' and len(c.beats)==20
    assert c.provenance.parameters['timing_candidate_confirmed'] is False
    assert c.provenance.parameters['candidate_source_job_id']=='original'


@pytest.mark.parametrize('error',['source','crop','duration','metered','density','fake_pass'])
def test_mismatched_or_failed_comparison_never_replaces_score(error):
    s,r=inputs()
    if error=='source':r['case']['source_url']='different'
    elif error=='crop':s.song.source_start_seconds=20
    elif error=='duration':r['case']['duration']=11
    elif error=='metered':s.analysis.timing_status='metered'
    elif error=='density':r['decoders']['dbn']['beats'][1]=.2
    elif error=='fake_pass':
        r['decoders']['dbn'].update(engineering_pass=True,projection={'bpm':120})
        r['decoders']['dbn']['downbeats']=[0,4,8]
    with pytest.raises(ValueError):build_checkpoint_candidate(s,r)


def test_timing_only_draft_keeps_original_guitar_inspection_audible():
    from app.exporters.midi import compile_playback_manifest
    s,r=inputs();s.rhythm.pattern_id='unmetered-chord-inspection-v1'
    original=compile_playback_manifest(s)
    candidate=compile_playback_manifest(build_checkpoint_candidate(s,r))
    assert original.events
    assert tuple(e for e in candidate.events if e.track=='guitar')==original.events
    assert any(e.track=='metronome' for e in candidate.events)
