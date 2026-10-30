from pathlib import Path
import json
import pytest
from httpx import ASGITransport,AsyncClient
from app.api import app
from app.models.score import SongScore
from app.exporters.midi import compile_playback_manifest
from app.services.revisions import RevisionStore


@pytest.mark.asyncio
async def test_example_works_without_local_jobs_audio_or_existing_revisions(tmp_path):
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        response=await client.get('/examples/little-hands')
    assert response.status_code==200
    data=response.json();score=SongScore.model_validate(data)
    assert score.song.source_type=='example' and score.analysis.timing_status=='unmetered'
    assert len(score.chords)==132 and not score.melody
    assert 'job_id' not in json.dumps(data) and '/home/' not in json.dumps(data)
    assert score.provenance.parameters['example_id']=='little-hands'
    assert score.song.source_url=='https://www.youtube.com/watch?v=5wq_uTMW0v8'
    events=compile_playback_manifest(score).events
    assert len(events)==132 and all(e.track=='guitar' for e in events)
    store=RevisionStore(tmp_path);revision=store.save(score)
    assert compile_playback_manifest(store.load(revision)).events==events
