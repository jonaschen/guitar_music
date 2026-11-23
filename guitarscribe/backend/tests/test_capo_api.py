import asyncio
import threading

from httpx import ASGITransport, AsyncClient
import pytest

from app.api import app
from app.models.analysis import ChordEvent
from app.models.score import SongScore
from app.services.capo import CapoAdvisor


@pytest.mark.asyncio
async def test_advice_contract_reports_missing_shapes_and_validates_preferences():
    score = SongScore(chords=[ChordEvent(id='c',start=0,end=1,symbol='C'),ChordEvent(id='x',start=1,end=2,symbol='Cmaj9')]).model_dump(mode='json')
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver') as client:
        response = await client.post('/scores/capo-recommendations',json=dict(score=score,max_capo=0,preferred_fret=3))
        assert response.status_code == 200
        row = response.json()[0]
        assert (row['covered_chords'],row['total_chords']) == (1,2)
        assert row['ranking_score'] >= row['difficulty']-.01
        for invalid in (-1,16,1.5):
            response = await client.post('/scores/capo-recommendations',json=dict(score=score,preferred_fret=invalid))
            assert response.status_code == 422
        score['guitar']['tuning'][0] = 38
        response = await client.post('/scores/capo-recommendations',json=dict(score=score))
        assert response.status_code == 422 and '標準調弦' in response.json()['detail']


@pytest.mark.asyncio
async def test_long_advice_calculation_does_not_block_health(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def slow(self, score, max_capo, preferred_fret):
        entered.set(); release.wait(3); return []
    monkeypatch.setattr(CapoAdvisor,'recommend',slow)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver') as client:
        task = asyncio.create_task(client.post('/scores/capo-recommendations',json=dict(score=SongScore().model_dump(mode='json'))))
        try:
            assert await asyncio.to_thread(entered.wait,1)
            response = await asyncio.wait_for(client.get('/health'),timeout=.5)
            assert response.status_code == 200 and not task.done()
        finally:
            release.set(); await task
