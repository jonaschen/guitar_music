"""Canonical boundary around legacy chord analyzers used during bake-offs."""

from __future__ import annotations

from ..protocols import ChordAnalyzer
from ...models.analysis import BeatAnalysis, BeatInfo, ChordAnalysis, ChordEvent
from ...models.audio import NormalizedAudio
from ...models.candidates import AnalyzerRun, ChordCandidateRegion, ChordResult, TimingResult


class CanonicalChordAnalyzerAdapter:
    def __init__(self, analyzer: ChordAnalyzer):
        self.analyzer = analyzer

    @staticmethod
    def _timing_projection(timing: TimingResult) -> BeatAnalysis:
        selected = timing.candidates[0]
        numerator = int(selected.meter.split("/", 1)[0])
        return BeatAnalysis(
            bpm=selected.bpm,
            time_signature=selected.meter,
            beats=[
                BeatInfo(
                    time=value,
                    beat=index % numerator + 1,
                    measure=index // numerator + 1,
                    confidence=selected.confidence,
                )
                for index, value in enumerate(selected.beats)
            ],
            downbeat_indices=list(range(selected.phase, len(selected.beats), numerator)),
            confidence=selected.confidence,
            engine=timing.run.engine,
            engine_version=timing.run.engine_version,
        )

    async def analyze_candidates(self, audio: NormalizedAudio, timing: TimingResult) -> ChordResult:
        analysis = await self.analyzer.analyze(audio, self._timing_projection(timing))
        analyzer_parameters = getattr(self.analyzer, "parameters", {})
        return ChordResult(
            run=AnalyzerRun(
                engine=analysis.engine or type(self.analyzer).__name__,
                engine_version=analysis.engine_version,
                parameters={
                    "timing_engine": timing.run.engine,
                    "timing_candidate_index": 0,
                    **analyzer_parameters,
                },
            ),
            regions=[
                ChordCandidateRegion(
                    start=event.start,
                    end=event.end,
                    label=event.symbol,
                    confidence=event.confidence,
                    label_candidates=event.label_candidates,
                )
                for event in analysis.chords
            ],
            key=analysis.key,
            mode=analysis.mode,
            confidence=analysis.confidence,
        )

    @staticmethod
    def project(result: ChordResult) -> ChordAnalysis:
        return ChordAnalysis(
            chords=[
                ChordEvent(
                    id=f"chord-{index + 1}",
                    start=region.start,
                    end=region.end,
                    symbol=region.label,
                    confidence=region.confidence,
                    label_candidates=region.label_candidates,
                )
                for index, region in enumerate(result.regions)
            ],
            key=result.key,
            mode=result.mode,
            confidence=result.confidence,
            engine=result.run.engine,
            engine_version=result.run.engine_version,
            parameters=result.run.parameters,
        )

    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis) -> ChordAnalysis:
        """Keep compatibility for callers that have not adopted TimingResult."""
        return await self.analyzer.analyze(audio, beats)
