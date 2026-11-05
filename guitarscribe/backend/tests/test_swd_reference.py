import csv
import hashlib

import mir_eval
import pytest

from app.evaluation.swd_reference import build_swd_annotation, swd_chord_label


@pytest.mark.parametrize(("source", "expected", "bass_pitch_class"), [
    ("C:maj/E", "C:maj/3", 4), ("Db:min/Ab", "Db:min/5", 8),
    ("C:7/Bb", "C:7/b7", 10), ("B:maj/F#", "B:maj/5", 6),
    ("C:maj/3", "C:maj/3", 4), ("N", "N", None),
])
def test_spelled_bass_is_preserved_as_relative_pitch(source, expected, bass_pitch_class):
    assert swd_chord_label(source) == expected
    root, _, bass = mir_eval.chord.encode(swd_chord_label(source))
    if bass_pitch_class is not None:
        assert (root + bass) % 12 == bass_pitch_class


def write_csv(path, fields, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(fields)
        writer.writerows(rows)


def test_only_recorded_downbeats_and_covered_time_are_used(tmp_path):
    chords, measures, audio = [tmp_path / name for name in ("chords.csv", "measures.csv", "clip.wav")]
    audio.write_bytes(b"source identity")
    write_csv(chords, ["start", "end", "shorthand"], [(0.2, 2, "C:maj/E"), (2, 6, "G:7")])
    write_csv(measures, ["start", "measure"], [(0.2, 1), (3.1, 2), (5.9, 2.999)])
    ref = build_swd_annotation(chords, measures, audio, "fixture", rights_note="Synthetic fixture", meter="4/4", clip_end=5)
    assert ref.excerpt_start == 0.2 and ref.excerpt_end == 5
    assert ref.beats == [] and ref.tempo_bpm is None
    assert [p.time for p in ref.downbeats] == [0.2, 3.1]
    assert ref.chords[0].label == "C:maj/3"
    assert ref.source_sha256 == hashlib.sha256(audio.read_bytes()).hexdigest()
    assert ref.annotation_status == "draft"


@pytest.mark.parametrize("problem", ["gap", "overlap", "bad_label", "duplicate_measure", "nan"])
def test_invalid_reference_fails_before_analysis(tmp_path, problem):
    chords, measures, audio = [tmp_path / name for name in ("chords.csv", "measures.csv", "clip.wav")]
    audio.write_bytes(b"source identity")
    chord_rows = [(0, 2, "C:maj"), (2, 5, "G:7")]
    measure_rows = [(0, 1), (3, 2)]
    if problem == "gap": chord_rows[1] = (2.1, 5, "G:7")
    if problem == "overlap": chord_rows[1] = (1.9, 5, "G:7")
    if problem == "bad_label": chord_rows[0] = (0, 2, "not-a-chord")
    if problem == "duplicate_measure": measure_rows[1] = (3, 1)
    if problem == "nan": chord_rows[0] = (float("nan"), 2, "C:maj")
    write_csv(chords, ["start", "end", "shorthand"], chord_rows)
    write_csv(measures, ["start", "measure"], measure_rows)
    with pytest.raises((ValueError, mir_eval.chord.InvalidChordException)):
        build_swd_annotation(chords, measures, audio, "fixture", rights_note="Synthetic fixture", meter="4/4", clip_end=5)
