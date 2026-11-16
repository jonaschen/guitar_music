"""Source-bound user revisions of a candidate, separate from independent references."""
import copy
import hashlib
import json

from .song_structure import LABELS


def candidate_digest(candidate: dict) -> str:
    return hashlib.sha256(json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def apply_feedback(candidate: dict, feedback: dict, audio_sha256: str) -> dict:
    if (feedback.get('schema_version') != 1 or feedback.get('job') != candidate['job']
            or feedback.get('audio_sha256') != audio_sha256
            or feedback.get('candidate_sha256') != candidate_digest(candidate)
            or feedback.get('independent_of_candidate') is not False
            or not feedback.get('reviewer') or not feedback.get('date')
            or candidate.get('feedback') is not None):
        raise ValueError('Feedback source, candidate version, or provenance mismatch')
    result = copy.deepcopy(candidate)
    original = candidate['sections']
    indices = {s['id']: i for i, s in enumerate(original)}
    if len(indices) != len(original):
        raise ValueError('Duplicate original section IDs')
    replacements, removed, touched = {}, set(), set()
    for operation in feedback['operations']:
        ids, kind, label = operation['ids'], operation['kind'], operation['label']
        if (not ids or len(set(ids)) != len(ids) or any(i not in indices or i in touched for i in ids)
                or kind not in ['merge', 'rename', 'confirm_name']
                or label not in {*LABELS, 'closing'}
                or label == 'closing' and operation.get('similar_to') != 'verse'):
            raise ValueError('Unknown or conflicting feedback operation')
        positions = [indices[i] for i in ids]
        if kind == 'merge' and (len(ids) < 2 or positions != list(range(positions[0], positions[0]+len(ids)))
                               or any(original[a]['end'] != original[b]['start']
                                      for a, b in zip(positions, positions[1:]))):
            raise ValueError('Merge requires adjacent original sections in chronological order')
        if kind == 'confirm_name' and any(original[i]['label'] != label for i in positions):
            raise ValueError('Name confirmation cannot silently change a label')
        touched.update(ids)
        groups = [positions] if kind == 'merge' else [[i] for i in positions]
        for group in groups:
            model = [copy.deepcopy(original[i]) for i in group]
            revised = copy.deepcopy(model[0])
            revised.update(id='+'.join(s['id'] for s in model), end=model[-1]['end'], label=label,
                           display_label='收尾段（較接近主歌）' if label == 'closing' else LABELS[label],
                           original_numbers=[i+1 for i in group], original_ids=[s['id'] for s in model],
                           model_sections=model, review_status='partial_user_feedback',
                           name_review_status='user_confirmed' if all(s['label'] == label for s in model) else 'user_corrected',
                           boundary_review_status='unreviewed')
            if label == 'closing':
                revised['similar_to'] = 'verse'
            if kind == 'merge':
                revised['removed_internal_boundaries'] = [s['end'] for s in model[:-1]]
                revised['model_end'] = model[-1]['model_end']
            replacements[group[0]] = revised
            removed.update(group[1:])
    result['sections'] = []
    for i, original_section in enumerate(original):
        if i in removed:
            continue
        section = replacements.get(i)
        if section is None:
            section = copy.deepcopy(original_section)
            section.update(original_numbers=[i+1], original_ids=[section['id']],
                           model_sections=[copy.deepcopy(original_section)],
                           name_review_status='unreviewed', boundary_review_status='unreviewed')
        result['sections'].append(section)
    result.update(section_count=len(result['sections']), feedback=copy.deepcopy(feedback),
                  reference_status='partial_user_feedback_after_candidate', ready_as_default=False)
    result['unresolved_seconds'] = sum(s['end']-s['start'] for s in result['sections']
                                       if s['label'] in ['start', 'end', 'unknown'])
    return result
