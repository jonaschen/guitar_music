import json
import pytest
from httpx import ASGITransport,AsyncClient
from app.web import create_app


@pytest.mark.asyncio
async def test_invitation_covers_bundle_and_api_with_separate_empty_database(tmp_path,monkeypatch):
    static=tmp_path/'site';static.mkdir();(static/'index.html').write_text('GuitarScribe preview')
    secret=tmp_path/'access.json';secret.write_text(json.dumps({'username':'friend','password':'test-invitation-123'}))
    monkeypatch.setenv('GUITARSCRIBE_WEB_ACCESS_FILE',str(secret));monkeypatch.setenv('GUITARSCRIBE_WEB_STATIC_DIR',str(static))
    monkeypatch.setenv('GUITARSCRIBE_WORK_DIR',str(tmp_path/'work'))
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://test') as client:
        for path in ['/','/backend/health','/backend/examples/little-hands','/backend/revisions/private']:
            response=await client.get(path);assert response.status_code==401
            assert 'Basic' in response.headers['www-authenticate']
        assert (await client.get('/',auth=('friend','wrong'))).status_code==401
        client.auth=('friend','test-invitation-123')
        assert (await client.get('/')).text=='GuitarScribe preview'
        assert (await client.get('/backend/health')).status_code==200
        assert (await client.get('/backend/revisions/private')).status_code==404
        example=(await client.get('/backend/examples/little-hands')).json()
        saved=(await client.post('/backend/revisions',json={'score':example})).json()
        assert (await client.get('/backend/revisions/'+saved['revision_id'])).json()==example
        assert (tmp_path/'work/revisions/guitarscribe.sqlite3').exists()
