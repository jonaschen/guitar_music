import mir_eval
import pytest

from app.evaluation.quality_report import _mir_eval_chord_label


@pytest.mark.parametrize('label,expected', [
    ('C6', 'C:maj6'), ('Cm6', 'C:min6'), ('Cm7b5', 'C:hdim7'),
    ('F#6', 'F#:maj6'), ('Bbm6', 'Bb:min6'), ('F#m7b5', 'F#:hdim7'),
    ('C6/E', 'C:maj6'), ('Bm7b5/F', 'B:hdim7'),
    ('C:maj6', 'C:maj6'), ('C:min6', 'C:min6'), ('C:hdim7/b5', 'C:hdim7/b5'),
    ('C', 'C:maj'), ('Cm', 'C:min'), ('C7', 'C:7'), ('Cmaj7', 'C:maj7'),
    ('Cm7', 'C:min7'), ('Cdim', 'C:dim'), ('Caug', 'C:aug'), ('N', 'N'),
])
def test_chordino_dictionary_labels_preserve_root_and_quality(label, expected):
    result = _mir_eval_chord_label(label)
    assert result == expected
    assert mir_eval.chord.root([result], [expected])[0] == 1


def test_unknown_quality_is_not_invented_as_major():
    assert _mir_eval_chord_label('Cmystery') == 'X'
