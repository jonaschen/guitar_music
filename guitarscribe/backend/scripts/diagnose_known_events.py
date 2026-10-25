"""Six synthetic event controls with handwritten expectations, not compiler oracles.

Run: python scripts/diagnose_known_events.py NEW_OUTPUT_DIRECTORY
Exit 1 means at least one diagnostic failed; artifacts are preserved.
"""
import argparse
from collections import defaultdict, deque
from io import BytesIO
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mido
from app.models.score import SongScore
from app.exporters.midi import compile_playback_manifest, export_midi


def controls():
    cases = []

    def case(name, duration, notes, beats=(), strokes=(), chords=(), capo=0, transpose=0, offset=0):
        # Lists below are independently authored event times and sounding pitches.
        reference = [dict(track="melody", pitch=p, start=a, end=b) for a, b, p in notes]
        reference += [dict(track="metronome", pitch=84 if beat == 1 else 76, start=t, end=t+.05)
                      for t, beat, _ in beats]
        for start, end, pitches in strokes:
            reference.extend(dict(track="guitar", pitch=p, start=start + i*.012, end=end)
                             for i, p in enumerate(pitches))
        score = dict(song=dict(title=name, duration_seconds=duration, source_start_seconds=offset),
                     analysis=dict(bpm=120, time_signature="4/4", capo=capo),
                     key_context=dict(transpose_semitones=transpose),
                     beats=[dict(time=t, beat=b, measure=m) for t, b, m in beats],
                     melody=[dict(id=f"n{i}", start=a, end=b, midi=p, note="diagnostic")
                             for i, (a, b, p) in enumerate(notes)],
                     chords=list(chords), rhythm=dict(subdivision=4, display=["D"], accents=[1]))
        cases.append(dict(name=name, score=score, reference=reference))

    def chord(id, start, end, symbol, frets):
        return dict(id=id, start=start, end=end, symbol=symbol, voicing_id=id,
                    available_voicings=[dict(id=id, symbol=symbol, shape_symbol=symbol, frets=frets)])

    case("rests_repeats_short_note", 2, [(0,.25,60),(.5,.505,62),(.505,.75,62),(1.25,1.5,60)])
    case("cross_bar_sustain", 4, [(1.75,2.25,67),(2.75,3.5,64)],
         [(0,1,1),(.5,2,1),(1,3,1),(1.5,4,1),(2,1,2),(2.5,2,2),(3,3,2),(3.5,4,2)])
    case("pickup_offbeat", 2, [(.375,.625,65),(.875,1.125,67)],
         [(.25,4,1),(.75,1,2),(1.25,2,2),(1.75,3,2)],
         [(.25,.75,[48,52]),(.75,1.25,[48,52]),(1.25,1.75,[48,52]),(1.75,2,[48,52])],
         [chord("c",0,2,"C",[None,3,2,None,None,None])])
    # Includes the next bar's boundary beat to specify the last uneven interval.
    case("variable_beat_spacing", 2.6, [(0,.5,60),(.5,1.1,62),(1.1,1.8,64),(1.8,2.6,65)],
         [(0,1,1),(.5,2,1),(1.1,3,1),(1.8,4,1),(2.6,1,2)],
         [(0,.5,[48,52]),(.5,1.1,[48,52]),(1.1,1.8,[48,52]),(1.8,2.6,[48,52])],
         [chord("c",0,2.6,"C",[None,3,2,None,None,None])])
    case("whole_half_crossbar_harmony", 6, [],
         [(0,1,1),(.5,2,1),(1,3,1),(1.5,4,1),(2,1,2),(2.5,2,2),
          (3,3,2),(3.5,4,2),(4,1,3),(4.5,2,3),(5,3,3),(5.5,4,3)],
         [(0,.5,[48,52]),(.5,1,[48,52]),(1,1.5,[48,52]),(1.5,2,[48,52]),
          (2,2.5,[43,47]),(2.5,3,[43,47]),(3,3.5,[50,57]),(3.5,4,[50,57]),
          (4,4.5,[50,57]),(4.5,5,[50,57]),(5,5.5,[48,52]),(5.5,6,[48,52])],
         [chord("c1",0,2,"C",[None,3,2,None,None,None]),
          chord("g",2,3,"G",[3,2,None,None,None,None]),
          chord("d",3,5,"D",[None,None,0,2,None,None]),
          chord("c2",5,6,"C",[None,3,2,None,None,None])])
    # Transposition is already reflected in melody MIDI. Capo affects shape
    # pitches once; source offset must never be added to analysis event times.
    case("source_offset_transpose_capo", 1, [(.125,.375,62),(.625,.875,66)],
         [(0,1,1),(.5,2,1)], [(0,.5,[50,54]),(.5,1,[50,54])],
         [chord("c",0,1,"D",[None,3,2,None,None,None])], capo=2, transpose=2, offset=18)
    return cases


def read_midi(data):
    midi = mido.MidiFile(file=BytesIO(data))
    pending, notes, errors = defaultdict(deque), [], []
    tick = 0
    seconds = 0.0
    tempo = 500000
    for message in mido.merge_tracks(midi.tracks):
        tick += message.time
        seconds += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        if message.type == "set_tempo":
            tempo = message.tempo
        elif message.type in ("note_on", "note_off"):
            key = (message.channel, message.note)
            if message.type == "note_on" and message.velocity:
                pending[key].append((tick, seconds))
            elif pending[key]:
                start_tick, start_seconds = pending[key].popleft()
                notes.append(dict(track={0:"melody",1:"guitar"}.get(message.channel,"unknown"),
                                  pitch=message.note, start=start_seconds, end=seconds,
                                  start_tick=start_tick, end_tick=tick))
            else:
                errors.append(dict(unmatched_off=list(key), tick=tick))
    errors.extend(dict(unclosed=list(key), count=len(value)) for key,value in pending.items() if value)
    return notes, errors, midi.ticks_per_beat


def compare(reference, actual, tolerance):
    key = lambda n:(n["track"],n["pitch"],n["start"],n["end"])
    expected, found = sorted(reference,key=key), sorted(actual,key=key)
    errors = []
    if len(expected) != len(found):
        errors.append(dict(kind="count", expected=len(expected), actual=len(found)))
    for i,(left,right) in enumerate(zip(expected,found)):
        if (left["track"],left["pitch"]) != (right["track"],right["pitch"]) or any(
                abs(left[field]-right[field]) > tolerance+1e-10 for field in ("start","end")):
            errors.append(dict(index=i, expected=left, actual=right))
    return errors


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    for item in controls():
        folder = output/item["name"]
        folder.mkdir()
        (folder/"reference.json").write_text(json.dumps(item["reference"],indent=2))
        score = SongScore.model_validate(item["score"])
        before = score.model_dump_json()
        (folder/"score.json").write_text(score.model_dump_json(indent=2))
        result = dict(name=item["name"], internal_tolerance_seconds=.001, export_tolerance_ticks=1)
        try:
            manifest = compile_playback_manifest(score)
            (folder/"manifest.json").write_text(manifest.model_dump_json(indent=2))
            actual = [dict(track=e.track,pitch=p,start=e.start+(e.pitch_offsets[i] if i<len(e.pitch_offsets) else 0),end=e.end)
                      for e in manifest.events for i,p in enumerate(e.pitches)]
            result["manifest_errors"] = compare(item["reference"], actual, .001)
            data = export_midi(score)
            (folder/"performance.mid").write_bytes(data)
            decoded, parse_errors, resolution = read_midi(data)
            (folder/"midi-events.json").write_text(json.dumps(decoded,indent=2))
            reference_ticks = [dict(track=n["track"],pitch=n["pitch"],
                                    start=n["start"]*score.analysis.bpm/60*resolution,
                                    end=n["end"]*score.analysis.bpm/60*resolution)
                               for n in item["reference"] if n["track"]!="metronome"]
            decoded_ticks = [dict(track=n["track"],pitch=n["pitch"],start=n["start_tick"],end=n["end_tick"]) for n in decoded]
            result["midi_errors"] = compare(reference_ticks,decoded_ticks,1)
            # Also compare seconds independently decoded through MIDI tempo;
            # correct tick positions alone would miss an incorrect tempo event.
            result["midi_seconds_errors"] = compare(
                [n for n in item["reference"] if n["track"] != "metronome"],
                decoded, 60 / score.analysis.bpm / resolution)
            result["midi_parse_errors"] = parse_errors
            result["score_unchanged"] = before == score.model_dump_json()
            result["passed"] = not any(result[k] for k in ("manifest_errors","midi_errors","midi_seconds_errors","midi_parse_errors")) and result["score_unchanged"]
        except Exception as error:
            result.update(passed=False,error=f"{type(error).__name__}: {error}")
        (folder/"report.json").write_text(json.dumps(result,indent=2))
        reports.append(result)
    summary = dict(cases=reports,passed=sum(r["passed"] for r in reports),failed=sum(not r["passed"] for r in reports),
                   limitations=["Synthetic event controls do not establish recognition quality.",
                                "MIDI omits metronome by existing export contract; compared only in manifest.",
                                "Capo/transpose case starts from already-transposed score, not the transpose API.",
                                "No WebAudio envelope or device timing validation."])
    (output/"report.json").write_text(json.dumps(summary,indent=2))
    return summary


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    report=run(args.output)
    print(json.dumps(report,indent=2))
    raise SystemExit(1 if report["failed"] else 0)
