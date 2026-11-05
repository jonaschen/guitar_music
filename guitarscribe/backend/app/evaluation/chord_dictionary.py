"""Symbolic dictionary availability, separate from acoustic/music correctness."""

from functools import lru_cache

import mir_eval

from .chord_errors import _identity, _pitch_classes, diagnostic_label


CATEGORIES = (
    "reference_unknown", "no_chord", "strict_label_match", "missing_inversion_only",
    "missing_omission_only", "missing_omission_and_inversion",
    "different_root_same_pitch_set_only", "candidate_pattern_absent",
)


def without_omissions(label):
    root, quality, degrees, bass = mir_eval.chord.split(label)
    return mir_eval.chord.join(root, quality, sorted(d for d in degrees if not d.startswith("*")), bass)


class DictionaryAvailability:
    def __init__(self, entries):
        self.entries = []
        seen = set()
        for entry in entries:
            if entry["index"] in seen or len(entry["weights"]) != 24:
                raise ValueError("Invalid or duplicate dictionary profile")
            seen.add(entry["index"])
            label = diagnostic_label(entry["label"])
            if label == "N":
                continue
            identity = _identity(label)
            # Actual upstream bins start on A (pitch class 9), not C.
            treble = {(i+9) % 12 for i, weight in enumerate(entry["weights"][12:]) if weight > 0}
            self.entries.append({**entry, "normalized": label, "identity": identity,
                                 "pitch_classes": _pitch_classes(label), "treble": treble})

    @lru_cache(maxsize=1024)
    def classify(self, label):
        label = diagnostic_label(label)
        if label in {"N", "X"}:
            return {"category": "no_chord" if label == "N" else "reference_unknown",
                    "different_root_same_pitch_set": False, "same_root_template_treble": False,
                    "matches": {}}
        identity = _identity(label)
        restored = _identity(without_omissions(label))
        pitches = _pitch_classes(label)
        base = {(identity[0]+i) % 12 for i, active in enumerate(identity[1]) if active}
        matches = {
            "strict": [e for e in self.entries if e["identity"] == identity],
            "same_root_quality": [e for e in self.entries if e["identity"][:2] == identity[:2]],
            "restored_omissions_strict": [e for e in self.entries if e["identity"] == restored],
            "restored_omissions_same_root_quality": [e for e in self.entries if e["identity"][:2] == restored[:2]],
            "different_root_same_pitch_set": [e for e in self.entries if e["identity"][0] != identity[0] and e["pitch_classes"] == pitches],
            "same_root_template_treble": [e for e in self.entries if e["identity"][0] == identity[0] and e["treble"] == base],
        }
        if matches["strict"]:
            category = "strict_label_match"
        elif matches["same_root_quality"]:
            category = "missing_inversion_only"
        elif matches["restored_omissions_strict"]:
            category = "missing_omission_only"
        elif matches["restored_omissions_same_root_quality"]:
            category = "missing_omission_and_inversion"
        elif matches["different_root_same_pitch_set"]:
            category = "different_root_same_pitch_set_only"
        else:
            category = "candidate_pattern_absent"
        return {
            "category": category,
            "different_root_same_pitch_set": bool(matches["different_root_same_pitch_set"]),
            "same_root_template_treble": bool(matches["same_root_template_treble"]),
            "matches": {name: [{"index": e["index"], "label": e["label"]} for e in entries]
                        for name, entries in matches.items()},
        }


def cross_tabulate(intervals, availability):
    totals = {key: {"reference_seconds": 0.0, "wrong_root_seconds": 0.0} for key in CATEGORIES}
    overlays = {key: {"reference_seconds": 0.0, "wrong_root_seconds": 0.0}
                for key in ("different_root_same_pitch_set", "same_root_template_treble")}
    rows = []
    for interval in intervals:
        match = availability.classify(interval["reference_label"])
        seconds = interval["seconds"]
        wrong_root = seconds if interval["category"] == "wrong_root" else 0.0
        totals[match["category"]]["reference_seconds"] += seconds
        totals[match["category"]]["wrong_root_seconds"] += wrong_root
        for name, value in overlays.items():
            if match[name]:
                value["reference_seconds"] += seconds
                value["wrong_root_seconds"] += wrong_root
        rows.append({"start": interval["start"], "end": interval["end"],
                     "reference": interval["reference_label"], "estimate": interval["estimate_label"],
                     "existing_error_category": interval["category"], **match})
    reference_seconds = sum(v["reference_seconds"] for v in totals.values())
    wrong_root_seconds = sum(v["wrong_root_seconds"] for v in totals.values())
    for value in totals.values():
        value["reference_fraction"] = value["reference_seconds"]/reference_seconds if reference_seconds else None
        value["wrong_root_fraction"] = value["wrong_root_seconds"]/wrong_root_seconds if wrong_root_seconds else None
    return {"reference_seconds": reference_seconds, "wrong_root_seconds": wrong_root_seconds,
            "categories": totals, "overlays_not_additive": overlays, "intervals": rows}
