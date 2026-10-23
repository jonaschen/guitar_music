"""Conservative consensus over persistent crossings from multiple signal representations."""

from __future__ import annotations

from itertools import product
import math
from statistics import median
from typing import Any


_ROUTES = (
    ("analysis-source", "cqt"),
    ("analysis-source", "stft"),
    ("accompaniment-stem", "cqt"),
    ("accompaniment-stem", "stft"),
)
_MAX_COMBINATIONS_PER_BOUNDARY = 4096


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _cluster_midpoint(cluster: Any) -> float | None:
    if not isinstance(cluster, (list, tuple)) or len(cluster) != 2:
        return None
    start, end = cluster
    if not _finite_number(start) or not _finite_number(end) or end < start:
        return None
    return (float(start) + float(end)) / 2


def select_boundary_consensus(
    report: dict[str, Any], max_spread: float = 0.15, max_shift: float = 0.45,
) -> dict[str, Any]:
    """Select a unique, bounded four-route crossing consensus per saved boundary.

    The function consumes only the harmony evidence report's four signal routes.
    User lyric landmarks, notes, and other report sections are intentionally not
    consulted. Rejected rows retain their route evidence for review.
    """
    if not _finite_number(max_spread) or max_spread < 0:
        raise ValueError("max_spread must be a finite non-negative number")
    if not _finite_number(max_shift) or max_shift < 0:
        raise ValueError("max_shift must be a finite non-negative number")

    sources = report.get("sources", {}) if isinstance(report, dict) else {}
    grouped: dict[tuple[str, str, float], dict[str, Any]] = {}
    for source, method in _ROUTES:
        source_data = sources.get(source, {}) if isinstance(sources, dict) else {}
        entries = source_data.get(method, []) if isinstance(source_data, dict) else []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            boundary = entry.get("boundary") if isinstance(entry, dict) else None
            if not isinstance(boundary, dict):
                continue
            from_label, to_label, saved_time = (
                boundary.get("from"), boundary.get("to"), boundary.get("saved_time")
            )
            if not isinstance(from_label, str) or not isinstance(to_label, str) or not _finite_number(saved_time):
                continue
            saved_time = float(saved_time)
            key = (from_label, to_label, round(saved_time, 9))
            group = grouped.setdefault(key, {
                "from": from_label,
                "to": to_label,
                "saved_time": saved_time,
                "routes": {route: {"clusters": [], "candidates": set()} for route in _ROUTES},
            })
            route = group["routes"][(source, method)]
            clusters = boundary.get("persistent_crossing_clusters", [])
            if not isinstance(clusters, list):
                continue
            for cluster in clusters:
                midpoint = _cluster_midpoint(cluster)
                if midpoint is None:
                    continue
                normalized_cluster = [float(cluster[0]), float(cluster[1])]
                route["clusters"].append(normalized_cluster)
                route["candidates"].add(midpoint)

    rows: list[dict[str, Any]] = []
    for key, group in sorted(grouped.items(), key=lambda item: (item[1]["saved_time"], item[0][:2])):
        route_evidence = []
        candidate_lists = []
        missing_routes = []
        for route_key in _ROUTES:
            route_data = group["routes"][route_key]
            candidates = sorted(route_data["candidates"])
            if not candidates:
                missing_routes.append({"source": route_key[0], "method": route_key[1]})
            candidate_lists.append(candidates)
            route_evidence.append({
                "source": route_key[0],
                "method": route_key[1],
                "clusters": route_data["clusters"],
                "candidate_midpoints": candidates,
            })

        evidence: dict[str, Any] = {"routes": route_evidence}
        target_time: float | None = None
        accepted = False
        if missing_routes:
            reason = "missing_route_evidence"
            evidence["missing_routes"] = missing_routes
        else:
            combination_count = math.prod(len(candidates) for candidates in candidate_lists)
            evidence["candidate_counts_by_route"] = [len(candidates) for candidates in candidate_lists]
            evidence["combination_count"] = combination_count
            if combination_count > _MAX_COMBINATIONS_PER_BOUNDARY:
                reason = "too_many_candidate_combinations"
                evidence["combination_limit"] = _MAX_COMBINATIONS_PER_BOUNDARY
            else:
                spread_combinations = []
                shift_combinations = []
                for selected in product(*candidate_lists):
                    spread = max(selected) - min(selected)
                    if spread > max_spread:
                        continue
                    center = float(median(selected))
                    shift = center - group["saved_time"]
                    combination = {
                        "candidate_times": list(selected),
                        "spread": spread,
                        "median": center,
                        "shift_from_saved": shift,
                    }
                    spread_combinations.append(combination)
                    if abs(shift) <= max_shift:
                        shift_combinations.append(combination)

                evidence["combinations_within_spread"] = spread_combinations
                evidence["combinations_with_limits"] = shift_combinations
                if not spread_combinations:
                    reason = "conflicting_candidates"
                elif not shift_combinations:
                    reason = "shift_exceeds_limit"
                elif len(shift_combinations) > 1:
                    reason = "multiple_consensus_combinations"
                else:
                    reason = "unique_consensus"
                    accepted = True
                    target_time = shift_combinations[0]["median"]

        rows.append({
            "saved_time": group["saved_time"],
            "target_time": target_time,
            "from": group["from"],
            "to": group["to"],
            "accepted": accepted,
            "reason": reason,
            "evidence": evidence,
        })
    return {
        "parameters": {
            "max_spread": max_spread,
            "max_shift": max_shift,
            "routes": [{"source": source, "method": method} for source, method in _ROUTES],
            "combination_limit_per_boundary": _MAX_COMBINATIONS_PER_BOUNDARY,
        },
        "limitations": [
            "The four signal routes are related representations of audio evidence, not independent ground truth.",
            "Persistent crossing midpoints are descriptive boundary candidates; they do not establish chord identity or a true boundary.",
            "A unique bounded consensus is not an automatic score or MIDI correction; retain human review and listening.",
            "Lyric marks are not read or used by this selector.",
        ],
        "rows": rows,
    }
