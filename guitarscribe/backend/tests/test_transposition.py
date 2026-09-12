import pytest

from app.models.analysis import AccidentalPreference, ChordEvent, ChordVoicing, MelodyAnalysis, MelodyNote
from app.fretboard.mapper import SimpleFretboardMapper
from app.models.score import AnalysisSummary, KeyContext, KeySignature, SongInfo, SongScore
from app.services.transposition import SHARP_NOTES, TranspositionService


def make_score() -> SongScore:
    return SongScore(
        song=SongInfo(title="Test Song", source_type="youtube", duration_seconds=120.0),
        analysis=AnalysisSummary(key="G", mode="major", bpm=120.0, time_signature="4/4", capo=0),
        key_context=KeyContext(
            source=KeySignature(key="G", mode="major"),
            target=KeySignature(key="G", mode="major"),
            shape=KeySignature(key="G", mode="major"),
            sounding=KeySignature(key="G", mode="major"),
        ),
        chords=[
            ChordEvent(id="c1", start=0.0, end=2.0, symbol="G"),
            ChordEvent(id="c2", start=2.0, end=4.0, symbol="D/F#"),
            ChordEvent(id="c3", start=4.0, end=6.0, symbol="Em7"),
        ],
        melody=[
            MelodyNote(id="n1", start=0.0, end=0.5, midi=67, note="G4"),
            MelodyNote(id="n2", start=0.5, end=1.0, midi=70, note="A#4"),
        ],
    )


def test_transpose_score_updates_chords_and_melody():
    service = TranspositionService()
    score = make_score()

    transposed = service.transpose_score(score, semitones=2, accidental_preference=AccidentalPreference.SHARPS)

    assert transposed.key_context.source.key == "G"
    assert transposed.key_context.target.key == "A"
    assert transposed.key_context.sounding.key == "A"
    assert transposed.key_context.transpose_semitones == 2
    assert transposed.key_context.audio_matches_notation is False
    assert [chord.symbol for chord in transposed.chords] == ["A", "E/G#", "F#m7"]
    assert transposed.chords[1].source_symbol == "D/F#"
    assert transposed.melody[0].midi == 69
    assert transposed.melody[0].note == "A4"
    assert transposed.melody[1].start == 0.5
    assert transposed.melody[1].end == 1.0
    assert score.chords[0].symbol == "G"


def test_transpose_score_updates_shape_key_for_capo():
    service = TranspositionService()
    score = make_score()

    transposed = service.transpose_score(score, semitones=2, capo=2, accidental_preference=AccidentalPreference.AUTO)

    assert transposed.analysis.capo == 2
    assert transposed.key_context.target.key == "A"
    assert transposed.key_context.shape.key == "G"
    assert transposed.chords[0].shape_symbol == "G"
    assert transposed.chords[1].shape_symbol == "D/F#"


def test_transpose_remaps_tab_for_the_new_pitch_and_capo():
    score = make_score()
    # G4 is available at fret 3 on string 1 without a capo.
    score.melody[0].string = 1
    score.melody[0].fret = 3

    transposed_without_capo = TranspositionService().transpose_score(score, semitones=2)
    transposed_with_capo = TranspositionService().transpose_score(score, semitones=2, capo=2)

    # A4 is fret 5 without a capo, or fret 3 relative to capo 2, on string 1.
    assert transposed_without_capo.melody[0].midi == 69
    assert transposed_without_capo.melody[0].string == 1
    assert transposed_without_capo.melody[0].fret == 5
    assert transposed_with_capo.melody[0].string == 1
    assert transposed_with_capo.melody[0].fret == 3
    # The original analysis result remains untouched.
    assert score.melody[0].fret == 3


def test_fretboard_mapper_respects_max_fret_limit():
    melody = SimpleFretboardMapper().map_notes(
        MelodyAnalysis(notes=[MelodyNote(id="n1", start=0.0, end=0.5, midi=67, note="G4")]),
        max_fret=2,
        preference="low_position",
    )

    # G4 needs at least fret 3 on a standard-tuned guitar.
    assert melody.notes[0].string is None
    assert melody.notes[0].fret is None


def test_transpose_rebuilds_a_playable_voicing_for_the_new_shape():
    score = make_score()
    score.chords[0].voicing_id = "open-g"
    score.chords[0].available_voicings = [ChordVoicing(id="open-g", symbol="G", shape_symbol="G", frets=[3, 2, 0, 0, 0, 3], fingers=[2, 1, 0, 0, 0, 3])]

    transposed = TranspositionService().transpose_score(score, semitones=2, capo=2)

    assert transposed.chords[0].shape_symbol == "G"
    assert transposed.chords[0].voicing_id == "open-g"
    assert transposed.chords[0].available_voicings[0].shape_symbol == "G"
    assert transposed.chords[0].available_voicings[0].capo == 2
    assert score.chords[0].voicing_id == "open-g"


def test_transpose_uses_flat_spelling_when_requested():
    service = TranspositionService()

    assert service.transpose_chord_symbol("F", 5, AccidentalPreference.FLATS) == "Bb"
    assert service.transpose_chord_symbol("C/E", 3, AccidentalPreference.FLATS) == "Eb/G"


@pytest.mark.parametrize("semitones", range(12))
def test_transpose_covers_every_pitch_class_for_key_chord_slash_bass_and_melody(semitones):
    service = TranspositionService()
    transposed = service.transpose_score(make_score(), semitones, AccidentalPreference.SHARPS)
    expected_root = SHARP_NOTES[(7 + semitones) % 12]  # G
    expected_slash_root = SHARP_NOTES[(2 + semitones) % 12]  # D
    expected_slash_bass = SHARP_NOTES[(6 + semitones) % 12]  # F#

    assert transposed.key_context.target.key == expected_root
    assert transposed.chords[0].symbol == expected_root
    assert transposed.chords[1].symbol == f"{expected_slash_root}/{expected_slash_bass}"
    assert transposed.melody[0].midi % 12 == (67 + semitones) % 12
    assert transposed.melody[1].midi % 12 == (70 + semitones) % 12
