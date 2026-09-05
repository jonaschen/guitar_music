from pydantic import BaseModel, Field

class WordTiming(BaseModel):
    id: str
    text: str
    start: float
    end: float
    confidence: float = 0.0
    origin: str = "alignment"

class LyricLine(BaseModel):
    id: str
    order: int
    start: float | None = None
    end: float | None = None
    text: str
    confidence: float = 1.0
    origin: str = "user"
    edited: bool = False
    words: list[WordTiming] = Field(default_factory=list)

class LyricsTrack(BaseModel):
    id: str = "lyrics-1"
    language: str = "und"
    source: str = "user-pasted"
    timing_level: str = "line"
    raw_text: str = ""
    revision: int = 1
    lines: list[LyricLine] = Field(default_factory=list)
