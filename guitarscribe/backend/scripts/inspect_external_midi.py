"""Read original external MIDI independently; never quantize, filter or render.

Usage: python scripts/inspect_external_midi.py INPUT.mid --csv INPUT.csv --output NEW_DIR
CSV comparisons cover NOTE onsets only when the export has no note-off columns.
"""
import argparse
from collections import Counter, defaultdict, deque
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics

import mido


def inspect(midi_path, csv_path=None):
    midi_path = Path(midi_path)
    midi = mido.MidiFile(midi_path)
    if midi.type == 2:
        raise ValueError("Type-2 MIDI has independent sequences; no single shared timeline")
    events = []
    for track_index, track in enumerate(midi.tracks):
        ticks = 0
        for order, message in enumerate(track):
            ticks += message.time
            events.append((ticks, track_index, order, message))
    events.sort(key=lambda item: item[:3])
    active, notes, errors, ambiguous = defaultdict(deque), [], [], []
    tempos = []
    tick, seconds, tempo = 0, 0., 500000
    for absolute, track, order, message in events:
        seconds += mido.tick2second(absolute-tick, midi.ticks_per_beat, tempo)
        tick = absolute
        if message.type == "set_tempo":
            tempo = message.tempo
            tempos.append(dict(tick=tick, seconds=seconds, microseconds_per_beat=tempo))
        if message.type not in ("note_on", "note_off"):
            continue
        key = (track, message.channel, message.note)
        if message.type == "note_on" and message.velocity > 0:
            if active[key]:
                ambiguous.append(dict(track=track, channel=message.channel, pitch=message.note, seconds=seconds))
            active[key].append(dict(track=track, channel=message.channel, midi=message.note,
                                    velocity=message.velocity, start=seconds, start_tick=tick,
                                    onset_tick_seconds=mido.tick2second(1, midi.ticks_per_beat, tempo)))
        elif active[key]:
            note = active[key].popleft()
            notes.append({**note, "end":seconds, "end_tick":tick, "duration":seconds-note["start"]})
        else:
            errors.append(dict(kind="unmatched_note_off", track=track, channel=message.channel,
                               midi=message.note, tick=tick, seconds=seconds))
    for key, pending in active.items():
        for note in pending:
            errors.append(dict(kind="unclosed_note", **note))
    notes.sort(key=lambda n:(n["start"],n["track"],n["channel"],n["midi"],n["end"]))
    overlaps = []
    for i,left in enumerate(notes):
        for j in range(i+1,len(notes)):
            right=notes[j]
            if right["start"]>=left["end"]:
                break
            duration=min(left["end"],right["end"])-right["start"]
            if duration>1e-9:
                overlaps.append(dict(left=i,right=j,seconds=duration,same_pitch=left["midi"]==right["midi"]))
    edges=sorted([(n["start"],1) for n in notes if n["duration"]>0]
                 +[(n["end"],-1) for n in notes if n["duration"]>0])
    count=maximum=0
    for _,delta in edges:
        count+=delta;maximum=max(maximum,count)
    report=dict(timing_interpretation="exported_times_not_proven_unquantized",
                midi_sha256=hashlib.sha256(midi_path.read_bytes()).hexdigest(),
                midi_type=midi.type,ticks_per_beat=midi.ticks_per_beat,track_count=len(midi.tracks),
                file_end_seconds=seconds,tempo_events=tempos,note_count=len(notes),
                first_onset=min((n["start"] for n in notes),default=None),
                last_note_end=max((n["end"] for n in notes),default=None),
                duration_min=min((n["duration"] for n in notes),default=None),
                duration_median=statistics.median(n["duration"] for n in notes) if notes else None,
                under_10ms=sum(n["duration"]<.01 for n in notes),
                under_100ms=sum(n["duration"]<.1 for n in notes),
                nonpositive_duration=sum(n["duration"]<=0 for n in notes),
                maximum_polyphony=maximum,overlap_pairs=overlaps,
                parse_errors=errors,ambiguous_repeated_note_ons=ambiguous,
                limitations=["Overlapping equal-pitch notes use FIFO note-off pairing; ambiguous cases are listed.",
                             "CSV NOTE rows in this schema contain onsets only: durations and note-offs cannot be independently validated.",
                             "Same-pitch chronological pairing is diagnostic; count mismatches invalidate a full timing-parity conclusion.",
                             "Timing parity does not establish musical transcription accuracy or explain quantization settings."])
    if csv_path is not None:
        csv_path=Path(csv_path)
        rows=[]
        with csv_path.open(newline="",encoding="utf-8-sig") as stream:
            for number,row in enumerate(csv.DictReader(stream),2):
                if row.get("Type","").strip() != "NOTE":
                    continue
                match=re.match(r"^(\d+)\b",row.get("Info","").strip())
                if not match:
                    raise ValueError(f"Unrecognized CSV pitch at line {number}")
                rows.append(dict(midi=int(match.group(1)),start=float(row["Time"]),line=number))
        expected,actual=defaultdict(list),defaultdict(list)
        for row in rows:expected[row["midi"]].append(row)
        for note in notes:actual[note["midi"]].append(note)
        comparisons=[]
        for pitch in sorted(set(expected)|set(actual)):
            for left,right in zip(sorted(expected[pitch],key=lambda n:n["start"]),sorted(actual[pitch],key=lambda n:n["start"])):
                error=right["start"]-left["start"]
                comparisons.append(dict(midi=pitch,csv_time=left["start"],midi_time=right["start"],
                                        signed_error_seconds=error,within_one_tick=abs(error)<=right["onset_tick_seconds"]+1e-6))
        differences=[r["signed_error_seconds"] for r in comparisons]
        report["csv_comparison"]=dict(csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            csv_note_count=len(rows),csv_pitch_counts=dict(Counter(r["midi"] for r in rows)),
            midi_pitch_counts=dict(Counter(n["midi"] for n in notes)),
            pitch_counts_equal=Counter(r["midi"] for r in rows)==Counter(n["midi"] for n in notes),
            paired=len(comparisons),within_one_tick=sum(r["within_one_tick"] for r in comparisons),
            median_signed_error_seconds=statistics.median(differences) if differences else None,
            max_absolute_error_seconds=max(map(abs,differences),default=None),
            comparisons=sorted(comparisons,key=lambda n:(n["csv_time"],n["midi"])))
    return notes, report


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi",type=Path)
    parser.add_argument("--csv",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    notes,report=inspect(args.midi,args.csv)
    args.output.mkdir(parents=True,exist_ok=False)
    for name,value in [("notes.json",notes),("report.json",report)]:
        (args.output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("overlap_pairs",)},indent=2))
