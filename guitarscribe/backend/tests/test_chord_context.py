"""Context changes require review without erasing accepted chord names."""
from copy import deepcopy
from tests.test_chord_practice import setup,edited,save
from app.services.chord_context import review_context
from app.services.root_practice import RootPracticeStore


def root_document(source):
    return dict(schema_version=1,source={k:v for k,v in source.items() if k!='audio_sha256'},segments=[
        dict(id='left',start=0.,end=4.,original_root=0,root=None,status='pending'),
        dict(id='phrase',start=4.,end=8.,original_root=0,root=9,status='confirmed'),
        dict(id='right',start=8.,end=12.,original_root=7,root=None,status='pending')])


def test_root_change_only_flags_overlapping_chords_and_never_rewrites_them(setup):
    s=setup;roots=RootPracticeStore(s.store.path.with_name('root-practice.sqlite3'));root=root_document(s.source);roots.save('song',root,0)
    result=save(s);before=deepcopy(result['document'])
    assert review_context(s.store,'song',before,s.structure_doc)['inside']['state']=='current'
    root['segments'][0].update(root=2,status='confirmed');roots.save('song',root,1)
    assert review_context(s.store,'song',before,s.structure_doc)['inside']['state']=='current'
    root['segments'][1]['root']=7;roots.save('song',root,2)
    review=review_context(s.store,'song',before,s.structure_doc)['inside']
    assert review['state']=='needs_review' and 'roots' in review['changed']
    assert s.store.read('song')['document']==before
    # Explicit adoption of a new segment records its current context.
    revised=deepcopy(before);revised['segments'][1]['id']='reconfirmed'
    save(s,revised,1)
    assert review_context(s.store,'song',revised,s.structure_doc)['reconfirmed']['state']=='current'
    save(s,before,2)
    assert review_context(s.store,'song',before,s.structure_doc)['inside']['state']=='needs_review'


def test_boundaries_and_source_changes_are_visible_but_renaming_is_not_a_harmony_change(setup):
    s=setup;save(s);doc=s.store.read('song')['document'];structure=deepcopy(s.structure_doc)
    structure['sections'][1]['display_label']='副歌二'
    assert review_context(s.store,'song',doc,structure)['inside']['state']=='current'
    structure['sections'][1]['start']=3.;structure['sections'][0]['end']=3.
    assert 'structure' in review_context(s.store,'song',doc,structure)['inside']['changed']
    roots=RootPracticeStore(s.store.path.with_name('root-practice.sqlite3'));root=root_document(s.source);root['source']['fingerprint']='c'*64;roots.save('song',root,0)
    assert review_context(s.store,'song',doc,s.structure_doc)['inside']['state']=='needs_review'


def test_missing_legacy_basis_is_unknown_not_a_false_confirmation(setup):
    s=setup;doc=edited(s)
    assert review_context(s.store,'song',doc,s.structure_doc)['inside']['state']=='unknown'
    assert not s.store.path.exists()
