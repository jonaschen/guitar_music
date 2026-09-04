import logging
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, MelodyAnalysis, MelodyNote, MelodyMode

logger = logging.getLogger(__name__)

NOTE_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']

def midi_to_note_name(midi: int) -> str:
    octave = (midi // 12) - 1
    note = NOTE_NAMES[midi % 12]
    return f"{note}{octave}"

class BasicPitchMelodyAnalyzer:
    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis) -> MelodyAnalysis:
        logger.info(f"Analyzing melody with basic-pitch for {audio.path}")
        try:
            from basic_pitch.inference import predict
        except ImportError as e:
            raise ImportError(f"Missing basic-pitch: {e}")

        try:
            model_output, midi_data, note_events = predict(str(audio.path))
            notes = []
            
            for i, note in enumerate(note_events):
                start, end, pitch, velocity, confidence = note
                if confidence < 0.5:
                    continue
                    
                notes.append(MelodyNote(
                    id=f"note-{i+1}",
                    start=float(start),
                    end=float(end),
                    midi=int(pitch),
                    note=midi_to_note_name(int(pitch)),
                    confidence=float(confidence)
                ))
                
            return MelodyAnalysis(
                notes=notes,
                mode=MelodyMode.VOCAL,
                confidence=0.8,
                engine="basic_pitch",
                engine_version="1.0"
            )
        except Exception as e:
            logger.error(f"Basic pitch analysis failed: {e}")
            raise RuntimeError(f"Basic pitch analysis failed: {e}")
