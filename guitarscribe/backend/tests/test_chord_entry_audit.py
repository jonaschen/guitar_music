import pytest

from app.services.chord_entry_audit import audit_chord_entries
from tests.test_chord_timing_candidate import source


def test_reports_measured_wait_without_editing_or_requiring_source_type():
    score=source();score.provenance.parameters.clear();before=score.model_dump_json()
    report=audit_chord_entries(score)
    assert len(report['issues'])==1
    issue=report['issues'][0]
    assert issue['downbeat_seconds']==2
    assert issue['detected_boundary_seconds']==2.04
    assert issue['first_attack_seconds']==2.5
    assert issue['wait_after_boundary_seconds']==pytest.approx(.46)
    assert issue['original_source_downbeat_seconds']==20
    assert issue['original_source_first_attack_seconds']==20.5
    assert issue['previous_beat_seconds']==1.5
    assert not report['applied'] and not report['saved']
    assert score.model_dump_json()==before


@pytest.mark.parametrize('mode',['continuous','sparse'])
def test_uses_selected_performance_not_original_schedule(mode):
    score=source()
    assert audit_chord_entries(score)['issues']
    assert not audit_chord_entries(score,mode)['issues']


@pytest.mark.parametrize('case',['early','offbeat','too_late','gap','short','same_label','no_stroke','no_beats','fast'])
def test_does_not_flag_other_boundary_types(case):
    score=source()
    if case in {'early','offbeat','too_late'}:
        t={'early':1.98,'offbeat':2.25,'too_late':2.06}[case]
        score.chords[0].end=score.chords[1].start=t
    if case=='gap':score.chords[0].end=2
    if case=='short':score.chords[1].end=2.12
    if case=='same_label':score.chords[1].symbol='C'
    if case=='no_stroke':score.rhythm.display[0]=None
    if case=='no_beats':score.beats=[]
    if case=='fast':
        for b in score.beats:b.time/=2
    assert not audit_chord_entries(score)['issues']


def test_manual_intent_reported_but_never_changed():
    score=source();score.chords[0].edited=True;before=score.model_dump_json()
    assert audit_chord_entries(score)['issues'][0]['contains_manual_edit']
    assert score.model_dump_json()==before


@pytest.mark.parametrize('case',['duplicate','overlap','beats','nan','duration'])
def test_rejects_invalid_timeline(case):
    score=source()
    if case=='duplicate':score.chords[1].id=score.chords[0].id
    if case=='overlap':score.chords[0].end=3
    if case=='beats':score.beats[1].time=0
    if case=='nan':score.chords[0].start=float('nan')
    if case=='duration':score.song.duration_seconds=float('nan')
    with pytest.raises(ValueError):audit_chord_entries(score)


@pytest.mark.asyncio
async def test_api_is_read_only_and_validates_mode():
    from httpx import AsyncClient,ASGITransport
    from app.api import app
    body={'score':source().model_dump(mode='json')}
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.post('/scores/chord-entry-audit',json=body)
        assert response.status_code==200
        assert len(response.json()['issues'])==1
        body['mode']='unknown'
        assert (await client.post('/scores/chord-entry-audit',json=body)).status_code==422
