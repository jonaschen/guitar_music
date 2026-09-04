import logging
import numpy as np
import librosa
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, BeatInfo

logger = logging.getLogger(__name__)

class LibrosaBeatAnalyzer:
    async def analyze(self, audio: NormalizedAudio) -> BeatAnalysis:
        logger.info(f"Analyzing beats for {audio.path}")
        try:
            y, sr = librosa.load(str(audio.path), sr=audio.sample_rate)
            
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo, beats_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            
            # Safely extract scalar BPM regardless of librosa version
            bpm = float(np.atleast_1d(tempo)[0])
            
            beat_times = librosa.frames_to_time(beats_frames, sr=sr)
            
            time_signature = "4/4"
            ts_num = 4
            
            beats = []
            downbeat_indices = []
            
            for i, t in enumerate(beat_times):
                measure = (i // ts_num) + 1
                beat_in_measure = (i % ts_num) + 1
                
                beats.append(BeatInfo(
                    time=float(t),
                    beat=beat_in_measure,
                    measure=measure,
                    confidence=0.8
                ))
                if beat_in_measure == 1:
                    downbeat_indices.append(i)
                    
            bpm_candidates = [bpm * 0.5, bpm, bpm * 2.0]
            
            return BeatAnalysis(
                bpm=bpm,
                bpm_candidates=bpm_candidates,
                time_signature=time_signature,
                beats=beats,
                downbeat_indices=downbeat_indices,
                confidence=0.8,
                engine="librosa",
                engine_version=librosa.__version__
            )
        except Exception as e:
            logger.error(f"Beat analysis failed: {e}")
            raise RuntimeError(f"Beat analysis failed: {e}")
