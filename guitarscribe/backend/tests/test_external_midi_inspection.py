"""Independent hand-authored MIDI/CSV fixtures; no GuitarScribe exporter."""
import importlib.util
from pathlib import Path

import mido
import pytest

spec = importlib.util.spec_from_file_location(
    "external_inspector", Path(__file__).resolve().parents[1]/"scripts/inspect_external_midi.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def save_midi(tmp_path, messages, tempos=None):
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    midi.tracks.append(mido.MidiTrack(tempos or [mido.MetaMessage("set_tempo",tempo=500000,time=0)]))
    midi.tracks.append(mido.MidiTrack(messages))
    path = tmp_path/"independent.mid"
    midi.save(path)
    return path


def test_tempo_changes_are_integrated_across_tracks_without_rescaling(tmp_path):
    path=save_midi(tmp_path,[mido.Message("note_on",note=60,velocity=91,time=240),
                             mido.Message("note_off",note=60,velocity=0,time=720)],
                   [mido.MetaMessage("set_tempo",tempo=500000,time=0),
                    mido.MetaMessage("set_tempo",tempo=1000000,time=480)])
    before=path.read_bytes()
    notes,report=inspector.inspect(path)
    assert len(notes)==1
    assert notes[0]["start"]==pytest.approx(.25)
    assert notes[0]["end"]==pytest.approx(1.5)
    assert notes[0]["start_tick"]==240 and notes[0]["end_tick"]==960
    assert notes[0]["velocity"]==91
    assert report["file_end_seconds"]==pytest.approx(1.5)
    assert [t["seconds"] for t in report["tempo_events"]]==[0,.5]
    assert report["timing_interpretation"]=="exported_times_not_proven_unquantized"
    assert path.read_bytes()==before


def test_overlapping_same_pitch_uses_fifo_and_reports_ambiguity(tmp_path):
    path=save_midi(tmp_path,[
        mido.Message("note_on",channel=1,note=60,velocity=90,time=0),
        mido.Message("note_on",channel=1,note=60,velocity=80,time=120),
        mido.Message("note_off",channel=1,note=60,velocity=0,time=120),
        mido.Message("note_on",channel=1,note=60,velocity=0,time=240),
    ])
    notes,report=inspector.inspect(path)
    assert [(n["start"],n["end"],n["velocity"]) for n in notes]==[(0,.25,90),(.125,.5,80)]
    assert report["maximum_polyphony"]==2
    assert report["overlap_pairs"]==[dict(left=0,right=1,seconds=.125,same_pitch=True)]
    assert len(report["ambiguous_repeated_note_ons"])==1
    assert not report["parse_errors"]


@pytest.mark.parametrize("rows,counts_equal,paired,within", [
    ("0,NOTE,62 (D4)\n",False,0,0),
    ("0,NOTE,60 (C4)\n0.2,NOTE,60 (C4)\n",False,1,1),
    ("0.25,NOTE,60 (C4)\n",True,1,0),
])
def test_csv_reports_pitch_count_and_timing_mismatches(tmp_path,rows,counts_equal,paired,within):
    path=save_midi(tmp_path,[mido.Message("note_on",note=60,velocity=90,time=0),
                            mido.Message("note_off",note=60,velocity=0,time=480)])
    csv_path=tmp_path/"independent.csv"
    csv_path.write_text("Time,Type,Info\n"+rows)
    notes,report=inspector.inspect(path,csv_path)
    comparison=report["csv_comparison"]
    assert len(notes)==1
    assert comparison["pitch_counts_equal"] is counts_equal
    assert comparison["paired"]==paired
    assert comparison["within_one_tick"]==within
    if counts_equal:
        assert comparison["max_absolute_error_seconds"]==pytest.approx(.25)


def test_unclosed_and_unmatched_messages_are_not_silently_repaired(tmp_path):
    path=save_midi(tmp_path,[mido.Message("note_off",note=62,time=0),
                            mido.Message("note_on",note=60,velocity=90,time=120)])
    notes,report=inspector.inspect(path)
    assert notes==[]
    assert [e["kind"] for e in report["parse_errors"]]==["unmatched_note_off","unclosed_note"]
