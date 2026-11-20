"""Net editing burden from retained candidate sections, never model accuracy."""
from ..services.song_structure import StructureDocument

EPS = 1e-7


def review_summary(value):
    doc = StructureDocument.model_validate(value)
    originals = {m.id: m for section in doc.sections for m in section.model_sections}
    baseline = sorted(originals.values(), key=lambda s: (s.start, s.end))
    complete = bool(baseline and abs(baseline[0].start) < EPS
                    and abs(baseline[-1].end-doc.source.duration) <= .05
                    and all(abs(a.end-b.start) < EPS for a,b in zip(baseline, baseline[1:])))
    result = dict(source=doc.source.model_dump(mode='json'), candidate_sha256=doc.candidate_sha256,
        current_sections=len(doc.sections), original_sections=len(baseline) if baseline else None,
        baseline_complete=complete, pending_sections=sum(
            s.name_review_status not in ('user_confirmed','user_corrected') or s.boundary_review_status!='user_confirmed'
            for s in doc.sections),
        confirmed_names=sum(s.name_review_status in ('user_confirmed','user_corrected') for s in doc.sections),
        confirmed_boundaries=sum(s.boundary_review_status=='user_confirmed' for s in doc.sections),
        name_changed_original_sections=None, boundary_changed_original_sections=None,
        net_changed_original_fraction=None, removed_internal_boundaries=None,
        added_internal_boundaries=None, section_count_reduction=None,
        semantic_accuracy=None, active_review_seconds=None, independent_reference=False,
        interpretation='Net differences from retained model sections, not click count, listening time or independent accuracy.')
    if not complete:
        return result
    old_edges=[s.end for s in baseline[:-1]]
    new_edges=[s.end for s in doc.sections[:-1]]
    removed=[t for t in old_edges if not any(abs(t-u)<EPS for u in new_edges)]
    added=[t for t in new_edges if not any(abs(t-u)<EPS for u in old_edges)]
    names=set(); boundaries=set()
    for old in baseline:
        if any(min(old.end,s.end)-max(old.start,s.start)>EPS and old.label!=s.label for s in doc.sections):
            names.add(old.id)
        if any(abs(old.start-t)<EPS or abs(old.end-t)<EPS for t in removed) or any(old.start+EPS<t<old.end-EPS for t in added):
            boundaries.add(old.id)
    result.update(name_changed_original_sections=len(names), boundary_changed_original_sections=len(boundaries),
        net_changed_original_fraction=len(names|boundaries)/len(baseline),
        removed_internal_boundaries=len(removed), added_internal_boundaries=len(added),
        section_count_reduction=len(baseline)-len(doc.sections))
    return result
