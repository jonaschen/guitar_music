import logging
from numbers import Real
from collections.abc import Mapping, Sequence
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
            model_output, midi_data, note_events = predict(
                str(audio.path),
                onset_threshold=0.25,
                frame_threshold=0.15,
                minimum_note_length=80,
            )
            logger.info("Basic Pitch produced %s candidate notes", len(note_events))
            notes = []
            
            for i, note in enumerate(note_events):
                parsed_note = _parse_note_event(note)
                if parsed_note is None:
                    logger.debug("Skipping unrecognized basic-pitch note event: %r", note)
                    continue

                start, end, pitch, confidence = parsed_note
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
                
            warnings = [] if notes else ["Basic Pitch returned no notes after its internal detection thresholds."]
            return MelodyAnalysis(
                notes=notes,
                mode=MelodyMode.VOCAL,
                confidence=0.8,
                engine="basic_pitch",
                engine_version="1.0",
                warnings=warnings
            )
        except Exception as e:
            logger.error(f"Basic pitch analysis failed: {e}")
            raise RuntimeError(f"Basic pitch analysis failed: {e}")


def _parse_note_event(note) -> tuple[float, float, int, float] | None:
    if isinstance(note, Mapping):
        start = note.get("start_time_s", note.get("start"))
        end = note.get("end_time_s", note.get("end"))
        pitch = note.get("pitch_midi", note.get("pitch"))
        confidence = note.get("confidence", note.get("amplitude", note.get("velocity", 1.0)))
        return _coerce_note_values(start, end, pitch, confidence)

    if isinstance(note, Sequence) and not isinstance(note, (str, bytes)):
        if len(note) < 3:
            return None

        start = note[0]
        end = note[1]
        pitch = note[2]
        # Basic Pitch sequence events use the fourth value for amplitude, not confidence.
        # Its inference thresholds have already selected these notes, so retain them with
        # a stable confidence suitable for downstream post-processing.
        confidence = 0.65

        return _coerce_note_values(start, end, pitch, confidence)

    return None


def _coerce_note_values(start, end, pitch, confidence) -> tuple[float, float, int, float] | None:
    if not all(isinstance(value, Real) for value in (start, end, pitch)):
        return None

    if not isinstance(confidence, Real):
        confidence = 1.0

    return float(start), float(end), int(pitch), float(confidence)
