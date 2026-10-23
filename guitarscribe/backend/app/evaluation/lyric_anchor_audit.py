"""Read-only comparisons of lyric marks with a score and compiled performance.

All signed errors are anchor time minus reference time, in seconds. No mark
is assumed to be a downbeat or a harmony change. Inputs are never modified.
"""
from math import isfinite


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _voicing(chord):
    choices = chord.get("available_voicings") or []
    selected = next((v for v in choices if v.get("id") == chord.get("voicing_id")),
                    choices[0] if choices else None)
    if selected is not None:
        return ("frets", tuple(selected.get("frets") or []))
    return ("id", chord.get("voicing_id"), chord.get("shape_symbol"))


def _nearest(items, time):
    return min(items, key=lambda item: (abs(item["time"] - time), item["time"]), default=None)


def audit_anchors(score: dict, manifest: dict, observations: list, analysis_start: float) -> dict:
    """Convert clip-relative marks to analysis seconds and report nearby events.

    ``seconds`` is the chosen mark; ``raw_seconds`` is retained for provenance
    and never silently substituted. Null or skipped marks have no comparisons.
    Equal-distance ties select the earlier reference deterministically.
    """
    if not _number(analysis_start) or analysis_start < 0:
        raise ValueError("analysis_start must be a finite nonnegative time")
    beats = [dict(time=b["time"], measure=b.get("measure"), beat=b.get("beat"))
             for b in score.get("beats", []) if _number(b.get("time"))]
    spans = []
    for chord in sorted(score.get("chords", []), key=lambda c: c["start"]):
        if not (_number(chord.get("start")) and _number(chord.get("end"))) or chord["end"] <= chord["start"]:
            raise ValueError("Chord spans must have finite increasing endpoints")
        signature = (chord.get("symbol"), _voicing(chord))
        if spans and spans[-1]["end"] == chord["start"] and spans[-1]["signature"] == signature:
            spans[-1]["end"] = chord["end"]
            spans[-1]["source_ids"].append(chord.get("id"))
        else:
            spans.append(dict(time=chord["start"], end=chord["end"], label=chord.get("symbol"),
                              signature=signature, source_ids=[chord.get("id")]))
    boundaries, strokes = [], []
    for span in spans:
        boundary = {k: span[k] for k in ("time", "end", "label", "source_ids")}
        firsts = []
        for event in manifest.get("events", []):
            if (event.get("track") != "guitar" or not event.get("pitches")
                    or event.get("source_id") is None or event.get("source_id") not in span["source_ids"]
                    or not _number(event.get("start"))):
                continue
            offsets = event.get("pitch_offsets") or []
            # Match PlaybackReference's zero-offset fallback; compiled manifests supply offsets.
            offsets = [offsets[i] if i < len(offsets) else 0 for i in range(len(event["pitches"]))]
            if not all(_number(offset) and offset >= 0 for offset in offsets):
                raise ValueError("Guitar offsets must be finite nonnegative times")
            firsts.append(dict(time=event["start"] + min(offsets), event_id=event.get("id"),
                               event_start=event["start"], stroke=event.get("stroke"),
                               label=span["label"], boundary_time=span["time"]))
        first = min(firsts, key=lambda e: e["time"], default=None)
        boundary["first_guitar_stroke"] = first
        boundaries.append(boundary)
        if first is not None:
            strokes.append(first)

    def comparison(reference, time):
        return None if reference is None else {**reference, "signed_error_seconds": time - reference["time"]}

    rows = []
    for observation in observations:
        seconds, raw = observation.get("seconds"), observation.get("raw_seconds")
        if any(value is not None and (not _number(value) or value < 0) for value in (seconds, raw)):
            raise ValueError("Anchor times must be null or finite nonnegative clip seconds")
        skipped = bool(observation.get("skipped"))
        time = None if skipped or seconds is None else analysis_start + seconds
        row = dict(anchor_index=observation.get("anchor_index"), raw_seconds=raw, seconds=seconds,
                   reviewed=bool(observation.get("reviewed")), skipped=skipped, analysis_time=time,
                   nearest_beat=None, nearest_chord_boundary=None, nearest_first_guitar_stroke=None)
        if time is not None:
            row.update(nearest_beat=comparison(_nearest(beats, time), time),
                       nearest_chord_boundary=comparison(_nearest(boundaries, time), time),
                       nearest_first_guitar_stroke=comparison(_nearest(strokes, time), time))
        rows.append(row)
    return dict(analysis_start=analysis_start, manifest_revision=manifest.get("revision"),
                signed_error_convention="anchor_minus_reference_seconds",
                counts=dict(total=len(rows), compared=sum(r["analysis_time"] is not None for r in rows),
                            skipped=sum(r["skipped"] for r in rows),
                            missing=sum(not r["skipped"] and r["seconds"] is None for r in rows),
                            reviewed=sum(r["reviewed"] for r in rows)), rows=rows,
                limitations=[
                    "Lyric stress does not imply beat 1 or a chord change.",
                    "Nearest-event matches are descriptive; no tempo correction or BPM inference is performed.",
                    "Human reaction latency and unreviewed marks can bias timing; raw marks are retained.",
                    "The caller must supply the matching score and manifest; this function does not verify source identity.",
                    "Chord references are merged span starts, including the first span and changes of voicing; gaps remain separate.",
                    "Nearest first stroke is selected independently; the nearest boundary also carries its own associated first stroke.",
                    "Missing guitar events are not invented; sample envelopes and device latency are not modeled.",
                ])
