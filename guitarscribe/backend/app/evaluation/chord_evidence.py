"""Duration-weighted root ranking, separate from decoder-selected chord labels."""
import numpy as np

from ..postprocess.harmony import parse_chord


def root_evidence_report(regions, labels, reference_chords):
    """Rank distinct roots by their best template score; retain every overlap.

    Exact ties use the pessimistic rank, preventing arbitrary template order
    from presenting ambiguous evidence as a confident correct root.
    Unpitched reference labels are reported separately, not scored as roots.
    """
    label_roots = [parse_chord(label) for label in labels]
    rows = []
    pitched = top1 = top3 = unknown = 0.0
    for start, end, scores in regions:
        root_scores = {}
        for parsed, score in zip(label_roots, scores, strict=True):
            if parsed:
                root_scores[parsed[1]] = max(root_scores.get(parsed[1], -np.inf), float(score))
        for chord in reference_chords:
            left, right = max(start, chord.start), min(end, chord.end)
            if right <= left:
                continue
            duration = right - left
            parsed = parse_chord(chord.label)
            if not parsed:
                unknown += duration
                continue
            root = parsed[1]
            score = root_scores.get(root)
            rank = (sum(value >= score for value in root_scores.values())
                    if score is not None else None)
            pitched += duration
            top1 += duration if rank == 1 else 0
            top3 += duration if rank is not None and rank <= 3 else 0
            rows.append({'start': left, 'end': right, 'reference': chord.label,
                         'reference_root_rank': rank, 'root_scores': root_scores})
    return {'pitched_overlap_seconds': pitched, 'unpitched_overlap_seconds': unknown,
            'top1_root_duration_fraction': top1 / pitched if pitched else None,
            'top3_root_duration_fraction': top3 / pitched if pitched else None,
            'overlaps': rows}
