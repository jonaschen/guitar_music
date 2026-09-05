import pytest
from app.services.lyrics import import_lrc, import_text
from app.api import LyricTimingRequest, update_lyric_timing
from app.models.lyrics import LyricsTrack

def test_import_text_preserves_repeated_lines():
    assert [line.text for line in import_text("Verse\nVerse\n\nChorus", "en").lines] == ["Verse", "Verse", "Chorus"]

def test_import_lrc_parses_timestamps_and_line_end():
    lyrics = import_lrc("[00:01.50]One\n[00:03.00]Two")
    assert lyrics.lines[0].start == 1.5
    assert lyrics.lines[0].end == 3.0


def test_export_lrc_omits_untimed_lines():
    from app.exporters.lrc import export_lrc
    lyrics = import_lrc("[00:01.50]One\n[00:03.00]Two")
    assert export_lrc(lyrics) == "[00:01.50]One\n[00:03.00]Two\n"

def test_manual_timing_can_be_updated():
    lyrics = import_text("One")
    line = lyrics.lines[0].model_copy(update={"start": 1.0, "end": 2.0, "edited": True})
    assert line.start == 1.0 and line.end == 2.0 and line.edited


@pytest.mark.asyncio
async def test_partial_lyric_timing_update_rejects_end_before_existing_start():
    lyrics = import_text("One")
    line = lyrics.lines[0].model_copy(update={"start": 2.0})
    score = __import__("app.models.score", fromlist=["SongScore"]).SongScore(lyrics=LyricsTrack(lines=[line]))

    with pytest.raises(Exception) as error:
        await update_lyric_timing(LyricTimingRequest(score=score, line_id=line.id, end=1.0))

    assert getattr(error.value, "status_code", None) == 422
