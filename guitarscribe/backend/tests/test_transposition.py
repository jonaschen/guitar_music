from app.models.analysis import AccidentalPreference, ChordEvent, MelodyNote
from app.models.score import AnalysisSummary, KeyContext, KeySignature, SongInfo, SongScore
from app.services.transposition import TranspositionService


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


def test_transpose_uses_flat_spelling_when_requested():
    service = TranspositionService()

    assert service.transpose_chord_symbol("F", 5, AccidentalPreference.FLATS) == "Bb"
    assert service.transpose_chord_symbol("C/E", 3, AccidentalPreference.FLATS) == "Eb/G"
