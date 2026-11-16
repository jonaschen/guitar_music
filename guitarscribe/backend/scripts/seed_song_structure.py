"""Seed reviewed candidates into an empty structure store via its authenticated API.

Existing structure documents are never overwritten. No root/Score API is written.
"""
import argparse
import base64
import json
from pathlib import Path
import sys
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.song_structure import load_ready_candidate
from app.evaluation.song_structure_feedback import apply_feedback, candidate_digest
from app.services.song_structure import StructureDocument, StructureSource


def document_for(candidate, original, source):
    source = StructureSource.model_validate(source).model_dump(mode='json')
    # Rebuild the reviewed view from its hash-bound feedback; never attach the
    # original candidate digest to independently edited model metadata.
    expected = (apply_feedback(original, candidate['feedback'], source['audio_sha256'])
                if candidate.get('feedback') is not None else original)
    if candidate != expected:
        raise ValueError('Review data differs from the original candidate and recorded feedback')
    if (candidate['job'] != source['job_id'] or candidate['fingerprint'] != source['fingerprint']
            or candidate['source_start'] != source['source_start']
            or abs(candidate['duration'] - source['duration']) > .05):
        raise ValueError('Reviewed candidate and current source differ')
    sections = []
    for i, section in enumerate(candidate['sections']):
        models = section.get('model_sections', [section])
        original_numbers = section.get('original_numbers', [i+1])
        models = [dict(id=m['id'], start=m['start'], end=m['end'], label=m['label'],
                       model_end=m['model_end'], original_number=number)
                  for m, number in zip(models, original_numbers, strict=True)]
        status = section.get('name_review_status', 'unreviewed')
        sections.append(dict(id=section['id'], start=section['start'], end=section['end'],
                             label=section['label'], display_label=section['display_label'],
                             name_review_status='tentative' if section['label'] == 'closing' else status,
                             boundary_review_status='unreviewed', model_sections=models,
                             note='使用者：收尾段，較接近主歌。' if section['label'] == 'closing' else ''))
    # The existing score duration may differ from decoded WAV duration by microseconds.
    # Keep raw model ends in provenance, and only reconcile the final editable endpoint.
    sections[-1]['end'] = source['duration']
    return StructureDocument.model_validate(dict(schema_version=1, source=source,
                                                 candidate_sha256=candidate_digest(original), sections=sections)).model_dump(mode='json')


def seed_candidates(candidates, runs, request, out):
    """Preflight the entire batch, then create only absent documents with CAS 0.

    A transport/CAS failure stops the batch without retries. Earlier successful
    songs remain safe: rerunning with a fresh audit directory skips exact matches.
    """
    if not isinstance(candidates, list) or not candidates:
        raise ValueError('At least one reviewed candidate is required')
    jobs = [candidate['job'] for candidate in candidates]
    if len(jobs) != len(set(jobs)) or any(job not in runs for job in jobs):
        raise ValueError('Each review requires one unique matching completed run')
    plans = []
    for candidate in candidates:
        job = candidate['job']
        original, manifest = runs[job]
        snapshot = request(job)
        source = snapshot.get('current_source')
        if (snapshot.get('job_id') != job or snapshot.get('source_matches') is not True
                or source is None or source.get('audio_sha256') != manifest['source']['audio_sha256']):
            raise ValueError('Current audio no longer matches the reviewed recording')
        version = snapshot.get('version')
        if (type(version) is not int or version < 0
                or (snapshot['document'] is None) != (version == 0)):
            raise ValueError('Unexpected structure snapshot version')
        document = document_for(candidate, original, source)
        if snapshot['document'] is not None and snapshot['document'] != document:
            raise ValueError('Existing user structure differs; refusing to overwrite it')
        plans.append((job, snapshot, document))
    out.mkdir(parents=True, exist_ok=False)
    results = []
    for job, snapshot, document in plans:
        filename = quote(job, safe='')
        (out/f'{filename}-before.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2)+'\n')
        created = snapshot['document'] is None
        saved = request(job, dict(expected_version=0, document=document)) if created else snapshot
        if (saved.get('job_id') != job or saved.get('document') != document
                or type(saved.get('version')) is not int or saved['version'] != (1 if created else snapshot['version'])
                or saved.get('source_matches') is not True or saved.get('current_source') != document['source']):
            raise ValueError('Save reply differs from the requested document; inspect server before retrying')
        (out/f'{filename}-saved.json').write_text(json.dumps(saved, ensure_ascii=False, indent=2)+'\n')
        results.append(dict(job=job, version=saved['version'], section_count=len(document['sections']), created=created))
    (out/'summary.json').write_text(json.dumps(results, indent=2)+'\n')
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--review-data', type=Path, required=True)
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--access-file', type=Path, required=True)
    parser.add_argument('--base', default='http://127.0.0.1:5273')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if urlparse(args.base).hostname not in ['127.0.0.1', 'localhost']:
        raise ValueError('This seeding tool only addresses the local service')
    credentials = json.loads(args.access_file.read_text())
    authorization = 'Basic '+base64.b64encode(f"{credentials['username']}:{credentials['password']}".encode()).decode()
    def request(job, payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        req = Request(args.base+'/backend/api/v1/jobs/'+quote(job, safe='')+'/song-structure', data=body,
                      headers={'Authorization': authorization, 'Content-Type': 'application/json'},
                      method='GET' if payload is None else 'PUT')
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    runs = {}
    for path in args.run:
        original = load_ready_candidate(path)
        if original['job'] in runs:
            raise ValueError('Multiple completed runs were supplied for the same job')
        runs[original['job']] = (original, json.loads((path/'manifest.json').read_text()))
    results = seed_candidates(json.loads(args.review_data.read_text()), runs, request, args.out)
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    main()
