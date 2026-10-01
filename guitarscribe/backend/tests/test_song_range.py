import pytest
from app.models.score import SongScore, SongInfo
from app.models.analysis import MelodyNote
from app.services.revisions import RevisionStore
from app.services.melody_edits import MelodyEditRequest, edit_melody


@pytest.mark.parametrize("start,end", [(-1, 3), (3, 3), (4, 2), (0, 11), (float("nan"), 3), (0, float("inf"))])
def test_invalid_song_range_is_rejected(start, end):
    with pytest.raises(ValueError):
        SongScore(song=SongInfo(duration_seconds=10), song_range={"start": start, "end": end})


def test_range_survives_save_and_edits_without_deleting_or_retiming_notes(tmp_path):
    score = SongScore(song=SongInfo(duration_seconds=10), song_range={"start": 2, "end": 8}, melody=[
        MelodyNote(id="intro", start=0, end=1, midi=60, note="C4", confidence=.5),
        MelodyNote(id="song", start=3, end=4, midi=64, note="E4", confidence=.5),
    ])
    store = RevisionStore(tmp_path)
    assert store.load(store.save(score)) == score
    result = edit_melody(MelodyEditRequest(score=score, operation="update", note_id="song", midi=65, start=3, end=4)).score
    assert result.song_range == score.song_range
    assert result.melody[0] == score.melody[0]
    assert result.melody[1].start == 3
    assert SongScore(song=score.song).song_range is None
