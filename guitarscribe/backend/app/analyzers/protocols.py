from typing import Protocol, runtime_checkable
from ..models.audio import SourceRequest, AudioAsset, NormalizedAudio
from ..models.analysis import BeatAnalysis, ChordAnalysis, MelodyAnalysis, MelodyMode, RhythmSuggestion, AudioFeatures, ChordComplexity
from ..models.score import SongScore
from ..models.candidates import ChordResult, MelodyCandidateResult, TimingResult

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
    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis, mode: MelodyMode = MelodyMode.VOCAL) -> MelodyAnalysis: ...

@runtime_checkable
class RhythmSuggester(Protocol):
    def suggest(self, beats: BeatAnalysis, chords: ChordAnalysis, features: AudioFeatures) -> RhythmSuggestion: ...

@runtime_checkable
class FretboardMapper(Protocol):
    def map_notes(self, melody: MelodyAnalysis) -> MelodyAnalysis: ...

@runtime_checkable
class ScoreExporter(Protocol):
    def export(self, score: SongScore) -> str: ...


@runtime_checkable
class TimingCandidateAnalyzer(Protocol):
    async def analyze_candidates(self, audio: NormalizedAudio) -> TimingResult: ...


@runtime_checkable
class ChordCandidateAnalyzer(Protocol):
    async def analyze_candidates(self, audio: NormalizedAudio, timing: TimingResult) -> ChordResult: ...


@runtime_checkable
class MelodyCandidateAnalyzer(Protocol):
    async def analyze_candidates(self, audio: NormalizedAudio, timing: TimingResult) -> MelodyCandidateResult: ...
