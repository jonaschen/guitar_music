import logging
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, ChordAnalysis, ChordEvent

logger = logging.getLogger(__name__)

class ChordinoChordAnalyzer:
    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis) -> ChordAnalysis:
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
            
            return ChordAnalysis(
                chords=events,
                key="C",
                mode="major",
                confidence=0.8,
                engine="chordino",
                engine_version="1.0"
            )
        except Exception as e:
            logger.error(f"Chordino analysis failed: {e}")
            raise RuntimeError(f"Chordino analysis failed: {e}")
