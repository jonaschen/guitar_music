import logging
import numpy as np
import librosa
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, BeatInfo
from ...models.candidates import AnalyzerRun, TimingCandidate, TimingResult

logger = logging.getLogger(__name__)

class LibrosaBeatAnalyzer:
    @staticmethod
    def _tempo_grid(beat_times: np.ndarray, multiplier: float) -> np.ndarray:
        if multiplier == 0.5:
            return beat_times[::2]
        if multiplier == 2.0 and len(beat_times) > 1:
            expanded = np.empty(len(beat_times) * 2 - 1, dtype=float)
            expanded[0::2] = beat_times
            expanded[1::2] = (beat_times[:-1] + beat_times[1:]) / 2
            return expanded
        return beat_times

    async def analyze_candidates(self, audio: NormalizedAudio) -> TimingResult:
        logger.info(f"Analyzing beats for {audio.path}")
        try:
            y, sr = librosa.load(str(audio.path), sr=audio.sample_rate)
            
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo, beats_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            
            # Safely extract scalar BPM regardless of librosa version
            bpm = float(np.atleast_1d(tempo)[0])
            beat_times = librosa.frames_to_time(beats_frames, sr=sr)
            if not np.isfinite(bpm) or bpm <= 0 or not len(beat_times):
                raise RuntimeError("No stable beat pulse was detected")

            candidates: list[TimingCandidate] = []
            for multiplier in (1.0, 0.5, 2.0):
                grid = self._tempo_grid(beat_times, multiplier)
                grid_values = [float(value) for value in grid]
                for first_downbeat_index in range(4):
                    candidates.append(TimingCandidate(
                        bpm=bpm * multiplier,
                        meter="4/4",
                        phase=first_downbeat_index,
                        beats=grid_values,
                        downbeats=grid_values[first_downbeat_index::4],
                        # Librosa estimates pulse, not meter/downbeat phase. Keep
                        # these deliberately unranked until audition/evaluation.
                        confidence=0.25 if multiplier == 1 else 0.125,
                    ))

            return TimingResult(
                run=AnalyzerRun(
                    engine="librosa",
                    engine_version=librosa.__version__,
                    parameters={"sample_rate": sr, "tempo_multipliers": "0.5,1,2", "meter": "4/4"},
                ),
                candidates=candidates,
            )
        except Exception as e:
            logger.error(f"Beat analysis failed: {e}")
            raise RuntimeError(f"Beat analysis failed: {e}")

    def project(self, result: TimingResult) -> BeatAnalysis:
        """Project the legacy phase-zero choice while preserving ambiguity upstream."""
        selected = result.candidates[0]
        beats = [
            BeatInfo(
                time=time,
                beat=index % 4 + 1,
                measure=index // 4 + 1,
                confidence=selected.confidence,
            )
            for index, time in enumerate(selected.beats)
        ]
        return BeatAnalysis(
            bpm=selected.bpm,
            bpm_candidates=[selected.bpm * 0.5, selected.bpm, selected.bpm * 2],
            time_signature=selected.meter,
            beats=beats,
            downbeat_indices=list(range(0, len(beats), 4)),
            confidence=selected.confidence,
            engine=result.run.engine,
            engine_version=result.run.engine_version,
            warnings=[
                "Librosa detects beat pulses but not downbeats; the legacy score currently assumes the first detected pulse is beat 1."
            ],
        )

    async def analyze(self, audio: NormalizedAudio) -> BeatAnalysis:
        return self.project(await self.analyze_candidates(audio))
