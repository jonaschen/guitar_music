import copy
import pytest
from app.evaluation.song_structure import summarize_candidate
from app.evaluation.song_structure_feedback import apply_feedback, candidate_digest


def fixture():
    labels = ['intro', 'intro', 'verse', 'verse', 'chorus', 'solo', 'verse',
              'verse', 'verse', 'chorus', 'chorus', 'chorus', 'outro', 'outro']
    candidate = summarize_candidate([dict(start=i, end=i+1, label=label) for i,label in enumerate(labels)], 14)
    candidate.update(job='song', fingerprint='f', title='song', source_start=0, duration=14)
    feedback = dict(schema_version=1, job='song', audio_sha256='audio', candidate_sha256=candidate_digest(candidate),
                    reviewer='user', date='2026-11-17', independent_of_candidate=False,
                    operations=[dict(kind='merge', ids=['section-1','section-2'], label='intro'),
                                dict(kind='rename', ids=['section-8','section-9'], label='chorus'),
                                dict(kind='rename', ids=['section-12'], label='closing', similar_to='verse'),
                                dict(kind='confirm_name', ids=['section-13','section-14'], label='outro')])
    return candidate, feedback


def test_feedback_applies_only_explicit_changes_preserving_model_and_unreviewed_boundaries():
    c,f = fixture();original=copy.deepcopy(c)
    result=apply_feedback(c,f,'audio')
    assert c == original
    assert len(result['sections']) == 13
    first=result['sections'][0]
    assert (first['start'], first['end'], first['original_numbers']) == (0,2,[1,2])
    assert [s['label'] for s in first['model_sections']] == ['intro','intro']
    by_original={n:s for s in result['sections'] for n in s['original_numbers']}
    assert by_original[8]['label'] == by_original[9]['label'] == 'chorus'
    assert by_original[12]['label'] == 'closing'
    assert by_original[12]['display_label'] == '收尾段（較接近主歌）'
    assert by_original[12]['similar_to'] == 'verse'
    assert by_original[13]['name_review_status'] == by_original[14]['name_review_status'] == 'user_confirmed'
    assert by_original[13]['id'] != by_original[14]['id']
    assert by_original[3]['name_review_status'] == 'unreviewed'
    assert all(s['boundary_review_status'] == 'unreviewed' for s in result['sections'])
    assert result['reference_status'] == 'partial_user_feedback_after_candidate'
    assert result['ready_as_default'] is False


@pytest.mark.parametrize('field,value', [('job','wrong'), ('audio_sha256','wrong'), ('candidate_sha256','wrong'), ('schema_version',2), ('independent_of_candidate',True)])
def test_feedback_rejects_wrong_source_version_or_reference_claim(field,value):
    c,f=fixture();f[field]=value
    with pytest.raises(ValueError):apply_feedback(c,f,'audio')


@pytest.mark.parametrize('operations', [
    [dict(kind='merge',ids=['section-1','section-3'],label='intro')],
    [dict(kind='merge',ids=['section-2','section-1'],label='intro')],
    [dict(kind='rename',ids=['section-99'],label='chorus')],
    [dict(kind='confirm_name',ids=['section-8'],label='outro')],
    [dict(kind='rename',ids=['section-8'],label='chorus'),dict(kind='rename',ids=['section-8'],label='verse')],
])
def test_invalid_or_ambiguous_operations_fail_atomically(operations):
    c,f=fixture();before=copy.deepcopy(c);f['operations']=operations
    with pytest.raises(ValueError):apply_feedback(c,f,'audio')
    assert c == before


def test_feedback_cannot_be_reapplied_to_renumbered_view():
    c,f=fixture()
    with pytest.raises(ValueError):apply_feedback(apply_feedback(c,f,'audio'),f,'audio')
