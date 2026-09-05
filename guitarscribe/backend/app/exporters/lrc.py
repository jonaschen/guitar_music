from ..models.lyrics import LyricsTrack


def export_lrc(lyrics: LyricsTrack) -> str:
    rows = []
    for line in lyrics.lines:
        if line.start is None:
            continue
        minutes, seconds = divmod(line.start, 60)
        rows.append(f"[{int(minutes):02d}:{seconds:05.2f}]{line.text}")
    return "\n".join(rows) + ("\n" if rows else "")
