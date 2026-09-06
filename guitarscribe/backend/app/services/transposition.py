import re
from typing import Optional

from ..models.analysis import AccidentalPreference
from ..models.analysis import MelodyAnalysis
from ..fretboard.mapper import SimpleFretboardMapper
from ..models.score import KeyContext, KeySignature, SongScore

NOTE_TO_PITCH = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}
SHARP_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NOTES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"}
CHORD_RE = re.compile(r"^([A-G](?:#|b)?)([^/]*)?(?:/([A-G](?:#|b)?))?$")


class TranspositionService:
    def __init__(self, fretboard_mapper: SimpleFretboardMapper | None = None):
        self.fretboard_mapper = fretboard_mapper or SimpleFretboardMapper()

    def transpose_score(
        self,
        score: SongScore,
        semitones: int,
        accidental_preference: AccidentalPreference = AccidentalPreference.AUTO,
        capo: Optional[int] = None,
    ) -> SongScore:
        normalized = self._normalize_semitones(semitones)
        result = score.model_copy(deep=True)
        source_key = result.key_context.source.key
        source_mode = result.key_context.source.mode
        target_key = self.transpose_note_name(source_key, normalized, accidental_preference, source_mode)
        capo_value = result.analysis.capo if capo is None else capo
        shape_key = self.transpose_note_name(target_key, -capo_value, accidental_preference, source_mode)

        result.analysis.key = target_key
        result.analysis.mode = source_mode
        result.analysis.capo = capo_value
        result.key_context = KeyContext(
            source=KeySignature(key=source_key, mode=source_mode),
            target=KeySignature(key=target_key, mode=source_mode),
            shape=KeySignature(key=shape_key, mode=source_mode),
            sounding=KeySignature(key=target_key, mode=source_mode),
            transpose_semitones=normalized,
            accidental_preference=accidental_preference,
            audio_matches_notation=normalized == 0,
        )

        for chord in result.chords:
            if chord.source_symbol is None:
                chord.source_symbol = chord.symbol
            chord.symbol = self.transpose_chord_symbol(chord.source_symbol, normalized, accidental_preference, source_mode)
            chord.shape_symbol = self.transpose_chord_symbol(chord.symbol, -capo_value, accidental_preference, source_mode)
            # A voicing belongs to its shape and capo; it must be selected again after either changes.
            chord.voicing_id = None
            chord.available_voicings = []

        for note in result.melody:
            if note.source_midi is None:
                note.source_midi = note.midi
            if note.source_note is None:
                note.source_note = note.note
            note.midi = note.source_midi + normalized
            note.note = self.note_name_from_midi(note.midi, target_key, accidental_preference, source_mode)

        # Transposition and capo changes alter which physical fret produces a
        # sounding melody pitch. Re-map only the notation data; no DSP rerun.
        remapped_melody = self.fretboard_mapper.map_notes(
            MelodyAnalysis(notes=result.melody),
            capo=capo_value,
        )
        result.melody = remapped_melody.notes

        return result

    def transpose_chord_symbol(
        self,
        symbol: str,
        semitones: int,
        accidental_preference: AccidentalPreference = AccidentalPreference.AUTO,
        mode: str = "major",
    ) -> str:
        match = CHORD_RE.match(symbol)
        if not match:
            return symbol

        root, quality, bass = match.groups()
        transposed_root = self.transpose_note_name(root, semitones, accidental_preference, mode)
        transposed_bass = ""
        if bass:
            transposed_bass = "/" + self.transpose_note_name(bass, semitones, accidental_preference, mode)
        return f"{transposed_root}{quality or ''}{transposed_bass}"

    def transpose_note_name(
        self,
        note: str,
        semitones: int,
        accidental_preference: AccidentalPreference = AccidentalPreference.AUTO,
        mode: str = "major",
    ) -> str:
        pitch = NOTE_TO_PITCH[note]
        target_pitch = (pitch + semitones) % 12
        prefer_flats = self._prefer_flats(note, accidental_preference, mode)
        names = FLAT_NOTES if prefer_flats else SHARP_NOTES
        return names[target_pitch]

    def note_name_from_midi(
        self,
        midi: int,
        key: str,
        accidental_preference: AccidentalPreference = AccidentalPreference.AUTO,
        mode: str = "major",
    ) -> str:
        pitch = midi % 12
        octave = (midi // 12) - 1
        names = FLAT_NOTES if self._prefer_flats(key, accidental_preference, mode) else SHARP_NOTES
        return f"{names[pitch]}{octave}"

    def _prefer_flats(
        self,
        key: str,
        accidental_preference: AccidentalPreference,
        mode: str,
    ) -> bool:
        if accidental_preference == AccidentalPreference.FLATS:
            return True
        if accidental_preference == AccidentalPreference.SHARPS:
            return False
        if "b" in key:
            return True
        if "#" in key:
            return False
        return key in FLAT_KEYS or (mode == "minor" and key in {"D", "G", "C", "F", "Bb", "Eb"})

    def _normalize_semitones(self, semitones: int) -> int:
        normalized = semitones % 12
        if normalized > 11:
            normalized -= 12
        if normalized > 6:
            normalized -= 12
        if normalized < -11:
            normalized += 12
        return normalized
