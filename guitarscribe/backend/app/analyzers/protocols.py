from typing import Protocol, runtime_checkable
from ..models.audio import SourceRequest, AudioAsset, NormalizedAudio
from ..models.analysis import BeatAnalysis, ChordAnalysis, MelodyAnalysis, RhythmSuggestion, AudioFeatures, ChordComplexity
from ..models.score import SongScore

@runtime_checkable
class AudioSource(Protocol):
    async def fetch(self, request: SourceRequest) -> AudioAsset: ...

@runtime_checkable
class AudioPreprocessor(Protocol):
    async def normalize(self, asset: AudioAsset) -> NormalizedAudio: ...

@runtime_checkable
class BeatAnalyzer(Protocol):
    async def analyze(self, audio: NormalizedAudio) -> BeatAnalysis: ...

@runtime_checkable
class ChordAnalyzer(Protocol):
    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis) -> ChordAnalysis: ...

@runtime_checkable
class MelodyAnalyzer(Protocol):
    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis) -> MelodyAnalysis: ...

@runtime_checkable
class RhythmSuggester(Protocol):
    def suggest(self, beats: BeatAnalysis, chords: ChordAnalysis, features: AudioFeatures) -> RhythmSuggestion: ...

@runtime_checkable
class FretboardMapper(Protocol):
    def map_notes(self, melody: MelodyAnalysis) -> MelodyAnalysis: ...

@runtime_checkable
class ScoreExporter(Protocol):
    def export(self, score: SongScore) -> str: ...
