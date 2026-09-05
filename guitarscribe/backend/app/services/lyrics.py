import re
from uuid import uuid4
from ..models.lyrics import LyricLine, LyricsTrack

LRC_TIMESTAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")

def import_text(text: str, language: str = "und") -> LyricsTrack:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return LyricsTrack(language=language, source="user-pasted", raw_text=text, lines=[LyricLine(id=uuid4().hex, order=index + 1, text=line) for index, line in enumerate(lines)])

def import_lrc(content: str, language: str = "und") -> LyricsTrack:
    parsed = []
    for raw_line in content.splitlines():
        timestamps = LRC_TIMESTAMP.findall(raw_line)
        text = LRC_TIMESTAMP.sub("", raw_line).strip()
        parsed.extend((int(minutes) * 60 + float(seconds), text) for minutes, seconds in timestamps)
    parsed.sort(key=lambda item: item[0])
    lines = [LyricLine(id=uuid4().hex, order=index + 1, start=start, end=parsed[index + 1][0] if index + 1 < len(parsed) else None, text=text) for index, (start, text) in enumerate(parsed)]
    return LyricsTrack(language=language, source="user-lrc", raw_text=content, lines=lines)
