from app.services.lyrics import import_lrc, import_text

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
