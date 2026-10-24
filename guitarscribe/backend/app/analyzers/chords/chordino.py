import logging
import hashlib
from pathlib import Path
from importlib.metadata import version
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, ChordAnalysis, ChordEvent
from ..worker import run_blocking_analysis
from .chromagram import estimate_key_from_chords

logger = logging.getLogger(__name__)

class ChordinoChordAnalyzer:
    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis) -> ChordAnalysis:
        return await run_blocking_analysis(self._analyze, audio, beats)

    def _analyze(self, audio: NormalizedAudio, beats: BeatAnalysis) -> ChordAnalysis:
        logger.info(f"Analyzing chords with chordino for {audio.path}")
        try:
            import vamp
            import librosa
        except ImportError as e:
            raise ImportError(f"Missing required dependency for chordino: {e}")

        try:
            y, sr = librosa.load(str(audio.path), sr=audio.sample_rate)
            data = vamp.collect(y, sr, "nnls-chroma:chordino")
            
            chords_data = data['list']
            events = []
            
            for i in range(len(chords_data)):
                event = chords_data[i]
                start = float(event['timestamp'])
                symbol = event['label']
                end = float(chords_data[i+1]['timestamp']) if i + 1 < len(chords_data) else audio.duration_seconds
                
                if symbol == "N":
                    continue
                    
                events.append(ChordEvent(
                    id=f"chord-{i+1}",
                    start=start,
                    end=end,
                    symbol=symbol,
                    confidence=0.9
                ))
            
            key, mode = estimate_key_from_chords(events)
            parameters = {'vamp_version': version('vamp')}
            library = Path(vamp.vampyhost.get_library_for('nnls-chroma:chordino'))
            parameters['chordino_library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
            return ChordAnalysis(
                chords=events,
                key=key,
                mode=mode,
                confidence=0.8,
                engine="chordino",
                engine_version="1.1-provenance",
                parameters=parameters,
                warnings=['Chordino chord confidence is not calibrated; the key is an estimate from detected harmony.'],
            )
        except Exception as e:
            logger.error(f"Chordino analysis failed: {e}")
            raise RuntimeError(f"Chordino analysis failed: {e}")
