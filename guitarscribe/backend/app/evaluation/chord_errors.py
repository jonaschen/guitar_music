"""Localize cached chord errors on a shared timeline without realignment."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
import math
import re
from typing import Any

import mir_eval
import numpy as np

from .annotations import QualityAnnotation
from .quality_report import _mir_eval_chord_label
from .swd_reference import swd_chord_label
from ..models.score import SongScore


CATEGORIES = (
    "reference_unknown", "estimate_unknown", "correct_no_chord", "missed_chord",
    "false_chord", "wrong_root", "same_root_wrong_quality", "bass_only", "exact_match",
)
_NOTE = re.compile(r"[A-G][#b]*\Z")
_INTERVALS = ("1", "b2", "2", "b3", "3", "4", "b5", "5", "b6", "6", "b7", "7")


@lru_cache(maxsize=2048)
def diagnostic_label(raw: str) -> str:
    """Preserve slash bass and Harte extensions; reject unsupported spellings."""
    label = raw.strip().replace("♯", "#").replace("♭", "b")
    if label in {"N", "NC", "N.C.", "no_chord"}:
        return "N"
    if label == "X":
        return "X"
    if not label:
        raise ValueError("Empty chord label is not an annotated rest")
    if ":" in label:
        return swd_chord_label(label)
    base, separator, bass = label.partition("/")
    normalized = _mir_eval_chord_label(base)
    if normalized == "X":
        raise ValueError(f"Unsupported chord label: {raw}")
    if separator:
        if _NOTE.fullmatch(bass):
            root = normalized.split(":", 1)[0]
            relative = (mir_eval.chord.pitch_class_to_semitone(bass)
                        - mir_eval.chord.pitch_class_to_semitone(root)) % 12
            bass = _INTERVALS[relative]
        normalized += "/" + bass
    mir_eval.chord.encode(normalized)
    return normalized


@lru_cache(maxsize=2048)
def _identity(label: str) -> tuple:
    if label in {"N", "X"}:
        return (label,)
    # encode() adds a non-chord bass into its bitmap. Decode the base separately
    # so a bass-only difference cannot masquerade as a quality difference.
    root_name, quality_name, degrees, _ = mir_eval.chord.split(label, reduce_extended_chords=True)
    root = mir_eval.chord.pitch_class_to_semitone(root_name)
    quality = mir_eval.chord.quality_to_bitmap(quality_name).copy()
    quality[0] = 1
    for degree in degrees:
        quality += mir_eval.chord.scale_degree_to_bitmap(degree, modulo=True)
    # encode() also re-inserts a default root bass after *1 removed the root.
    # Keep explicit omitted tones in this diagnostic's base-quality comparison.
    quality = (quality > 0).astype(int)
    bass = mir_eval.chord.encode(label, True)[2]
    return int(root), tuple(int(v) for v in quality), int(bass)


def _pitch_classes(label: str) -> set[int]:
    identity = _identity(label)
    if len(identity) == 1:
        return set()
    root, quality, bass = identity
    pitches = {(root+i) % 12 for i, active in enumerate(quality) if active}
    if "/" in label:
        pitches.add((root+bass) % 12)
    return pitches


def _interior_seconds(start: float, end: float, boundaries: list[float], tolerance: float) -> float:
    """Duration outside the UNION of reference transition tolerance windows."""
    cursor, near = start, 0.0
    for t in sorted(boundaries):
        left, right = max(start, t-tolerance), min(end, t+tolerance)
        if right > max(cursor, left):
            near += right-max(cursor, left)
            cursor = right
    return max(0.0, end-start-near)


@dataclass(frozen=True)
class Span:
    start: float
    end: float
    raw: str | None
    label: str
    scoring_label: str
    origin: str


def _timeline(regions, start: float, end: float, *, reference: bool) -> list[Span]:
    spans = []
    cursor = start
    for region in sorted(regions, key=lambda item: item.start):
        if (not math.isfinite(region.start) or not math.isfinite(region.end)
                or region.start < 0 or region.end <= region.start):
            raise ValueError("Chord intervals must be finite, nonnegative and positive length")
        left, right = max(start, region.start), min(end, region.end)
        if right <= left:
            continue
        if left < cursor:
            raise ValueError("Overlapping chord intervals cannot be diagnosed")
        if left > cursor:
            fill = "X" if reference else "N"
            spans.append(Span(cursor, left, None, fill, fill, "gap"))
        raw = region.label if reference else region.symbol
        full = diagnostic_label(raw)
        # Preserve the existing evaluation projection for root/majmin parity.
        scoring = _mir_eval_chord_label(raw)
        if ":" in scoring:
            scoring = swd_chord_label(scoring)
        spans.append(Span(left, right, raw, full, scoring, "annotated" if reference else "predicted"))
        cursor = right
    if cursor < end:
        fill = "X" if reference else "N"
        spans.append(Span(cursor, end, None, fill, fill, "gap"))
    return spans


def _category(reference: str, estimate: str) -> str:
    if reference == "X":
        return "reference_unknown"
    if estimate == "X":
        return "estimate_unknown"
    if reference == "N":
        return "correct_no_chord" if estimate == "N" else "false_chord"
    if estimate == "N":
        return "missed_chord"
    r, e = _identity(reference), _identity(estimate)
    if r[0] != e[0]:
        return "wrong_root"
    if r[1] != e[1]:
        return "same_root_wrong_quality"
    return "bass_only" if r[2] != e[2] else "exact_match"


def _boundaries(spans: list[Span]) -> list[dict[str, Any]]:
    # Excerpt endpoints, duplicate segments and unknown-reference edges are not
    # true annotated chord transitions.
    return [{"time": b.start, "before": a.label, "after": b.label}
            for a, b in zip(spans, spans[1:])
            if a.label != "X" and b.label != "X" and _identity(a.label) != _identity(b.label)]


def _boundary_report(reference: list[Span], estimated: list[Span], tolerance: float) -> dict:
    refs, ests = _boundaries(reference), _boundaries(estimated)
    # Estimate transitions bordering unknown reference coverage are not scored.
    def reference_known_around(t):
        return any(s.start < t <= s.end and s.label != "X" for s in reference) and any(
            s.start <= t < s.end and s.label != "X" for s in reference)
    excluded = [e for e in ests if not reference_known_around(e["time"])]
    ests = [e for e in ests if reference_known_around(e["time"])]
    matches = mir_eval.util.match_events(
        np.asarray([r["time"] for r in refs]), np.asarray([e["time"] for e in ests]), tolerance)
    paired = [{"reference": refs[r], "estimate": ests[e],
               "lag_seconds": ests[e]["time"] - refs[r]["time"]} for r, e in matches]
    matched_r, matched_e = {r for r, _ in matches}, {e for _, e in matches}
    precision = len(matches) / len(ests) if ests else None
    recall = len(matches) / len(refs) if refs else None
    return {
        "tolerance_seconds": tolerance,
        "matching": "one-to-one maximum-cardinality, label-independent; positive lag means estimate late",
        "reference_count": len(refs), "estimated_count": len(ests),
        "matched_count": len(matches), "precision": precision, "recall": recall,
        "unmatched_reference_count": len(refs)-len(matches),
        "unmatched_estimate_count": len(ests)-len(matches),
        "excluded_estimate_unknown_reference_count": len(excluded),
        "matched_mean_absolute_lag_seconds": float(np.mean([abs(p["lag_seconds"]) for p in paired])) if paired else None,
        "pairs": paired,
        "unmatched_reference": [r for i, r in enumerate(refs) if i not in matched_r],
        "unmatched_estimate": [e for i, e in enumerate(ests) if i not in matched_e],
        "excluded_estimate_unknown_reference": excluded,
    }


def diagnose_chord_errors(score: SongScore, annotation: QualityAnnotation, *,
                          boundary_tolerance: float = 0.25) -> dict[str, Any]:
    """Exclusive label-error seconds, orthogonal vocabulary and boundary evidence."""
    start, end = annotation.excerpt_start, annotation.excerpt_end
    if not all(math.isfinite(v) for v in (start, end, boundary_tolerance)) or end <= start or boundary_tolerance < 0:
        raise ValueError("Invalid evaluation window or boundary tolerance")
    reference = _timeline(annotation.chords, start, end, reference=True)
    estimated = _timeline(score.chords, start, end, reference=False)
    reference_boundaries = [b["time"] for b in _boundaries(reference)]
    rows = []
    i = j = 0
    while i < len(reference) and j < len(estimated):
        r, e = reference[i], estimated[j]
        left, right = max(r.start, e.start), min(r.end, e.end)
        if right > left:
            category = _category(r.label, e.label)
            rows.append({
                "start": left, "end": right, "seconds": right-left,
                "reference_raw": r.raw, "estimate_raw": e.raw,
                "reference_label": r.label, "estimate_label": e.label,
                "reference_origin": r.origin, "estimate_origin": e.origin,
                "reference_scoring_label": r.scoring_label, "estimate_scoring_label": e.scoring_label,
                "category": category,
                "reference_omits_root": r.label not in {"N", "X"} and "*1" in mir_eval.chord.split(r.label)[2],
                "same_absolute_pitch_classes": (_pitch_classes(r.label) == _pitch_classes(e.label))
                    if r.label not in {"N", "X"} and e.label not in {"N", "X"} else None,
                "estimated_root_is_reference_tone": _identity(e.label)[0] in _pitch_classes(r.label)
                    if category == "wrong_root" else None,
                "wrong_root_interior_seconds": _interior_seconds(left, right, reference_boundaries, boundary_tolerance)
                    if category == "wrong_root" else 0.0,
            })
        if r.end <= e.end:
            i += 1
        if e.end <= r.end:
            j += 1

    refs = [row["reference_scoring_label"] for row in rows]
    ests = [row["estimate_scoring_label"] for row in rows]
    metric_summary = {}
    for name, comparator in (("root", mir_eval.chord.root), ("majmin", mir_eval.chord.majmin)):
        values = comparator(refs, ests)
        for row, value in zip(rows, values):
            row[f"{name}_correct"] = None if value < 0 else bool(value)
        scored = sum(row["seconds"] for row in rows if row[f"{name}_correct"] is not None)
        correct = sum(row["seconds"] for row in rows if row[f"{name}_correct"] is True)
        metric_summary[name] = {"scored_seconds": scored, "unscored_seconds": end-start-scored,
                                "correct_seconds": correct, "error_seconds": scored-correct,
                                "scored_fraction": scored/(end-start),
                                "accuracy": correct/scored if scored else None}

    category_seconds = {name: 0.0 for name in CATEGORIES}
    confusions = defaultdict(float)
    for row in rows:
        category_seconds[row["category"]] += row["seconds"]
        if row["category"] not in {"reference_unknown", "correct_no_chord", "exact_match"}:
            confusions[(row["reference_label"], row["estimate_label"], row["category"])] += row["seconds"]
    scored = end-start-category_seconds["reference_unknown"]
    error = scored-category_seconds["correct_no_chord"]-category_seconds["exact_match"]
    summary = {
        "interval": [start, end], "duration_seconds": end-start,
        "known_reference_seconds": scored, "reference_unknown_seconds": category_seconds["reference_unknown"],
        "label_error_seconds": max(0.0, error), "category_seconds": category_seconds,
        "overlays_not_additive": {
            "wrong_root_interior_seconds": sum(r["wrong_root_interior_seconds"] for r in rows),
            "wrong_root_shared_pitch_set_seconds": sum(r["seconds"] for r in rows
                if r["category"] == "wrong_root" and r["same_absolute_pitch_classes"]),
            "wrong_root_is_reference_tone_seconds": sum(r["seconds"] for r in rows
                if r["estimated_root_is_reference_tone"]),
            "reference_omits_root_seconds": sum(r["seconds"] for r in rows if r["reference_omits_root"]),
        },
        "metrics": metric_summary,
        "confusions": [{"reference": r, "estimate": e, "category": c, "seconds": seconds}
                       for (r, e, c), seconds in sorted(confusions.items(), key=lambda x: (-x[1], x[0]))],
        "examples": {category: sorted((row for row in rows if row["category"] == category),
                                     key=lambda row: -row["seconds"])[:3]
                     for category in CATEGORIES if category not in {"exact_match", "correct_no_chord"}},
    }
    return {"schema_version": "1.0", "recording_id": annotation.recording_id,
            "summary": summary, "intervals": rows,
            "boundaries": _boundary_report(reference, estimated, boundary_tolerance)}
