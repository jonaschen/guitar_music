import logging
import hashlib
from pathlib import Path
from importlib.metadata import version
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, ChordAnalysis, ChordEvent
from ..worker import run_blocking_analysis
from .chromagram import estimate_key_from_chords

logger = logging.getLogger(__name__)


def decode_chord_events(chords_data, duration_seconds):
    """Intersect Vamp regions with the audio; padding is not playable time."""
    events = []
    for i, event in enumerate(chords_data):
        start = max(0.0, float(event['timestamp']))
        end = min(duration_seconds, float(chords_data[i+1]['timestamp'])
                  if i + 1 < len(chords_data) else duration_seconds)
        if event['label'] == 'N' or end <= start:
            continue
        events.append(ChordEvent(id=f'chord-{i+1}', start=start, end=end,
                                 symbol=event['label'], confidence=0.9))
    return events


class ChordinoChordAnalyzer:
    supports_unmetered = True
    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis | None) -> ChordAnalysis:
        return await run_blocking_analysis(self._analyze, audio, beats)

    def _analyze(self, audio: NormalizedAudio, beats: BeatAnalysis | None) -> ChordAnalysis:
        # Chordino uses audio only; an inspection can run without a valid meter.
        logger.info(f"Analyzing chords with chordino for {audio.path}")
        try:
            import vamp
            import librosa
        except ImportError as e:
            raise ImportError(f"Missing required dependency for chordino: {e}")

        try:
            y, sr = librosa.load(str(audio.path), sr=audio.sample_rate)
            data = vamp.collect(y, sr, "nnls-chroma:chordino")
            
            events = decode_chord_events(data['list'], audio.duration_seconds)
            
            key, mode = estimate_key_from_chords(events)
            parameters = {'vamp_version': version('vamp'), 'chordino_region_bounds': 'audio-intersection-v1'}
            library = Path(vamp.vampyhost.get_library_for('nnls-chroma:chordino'))
            parameters['chordino_library_sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
            return ChordAnalysis(
                chords=events,
                key=key,
                mode=mode,
                confidence=0.8,
                engine="chordino",
                engine_version="1.2-audio-bounds",
                parameters=parameters,
                warnings=['Chordino chord confidence is not calibrated; the key is an estimate from detected harmony.'],
            )
        except Exception as e:
            logger.error(f"Chordino analysis failed: {e}")
            raise RuntimeError(f"Chordino analysis failed: {e}")
