import pytest
from app.services.revisions import RevisionStore
from app.models.score import SongScore

def test_history_groups_forks_and_preserves_original(tmp_path):
    store=RevisionStore(tmp_path)
    original=SongScore()
    first=store.save(original)
    edited=original.model_copy(deep=True)
    edited.song.title='Edited'
    second=store.fork(first,edited)
    unrelated=store.save(SongScore())
    assert [r['id'] for r in store.history(second)] == [second,first]
    assert unrelated not in [r['id'] for r in store.history(first)]
    assert store.load(first).song.title != 'Edited'
    with pytest.raises(FileNotFoundError): store.history('missing')
