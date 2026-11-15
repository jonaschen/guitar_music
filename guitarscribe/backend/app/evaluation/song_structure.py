"""Read-only structure candidate validation; never changes root decisions or Score."""
import hashlib
import math
import json
from pathlib import Path

LABELS = {
    'intro': '前奏', 'verse': '主歌', 'chorus': '副歌', 'bridge': '橋段', 'outro': '尾奏',
    'inst': '器樂段（間奏候選）', 'solo': '獨奏段（間奏候選）', 'break': '停頓／過渡段',
    'start': '開頭未判定', 'end': '結尾未判定', 'unknown': '未判定',
}


def verify_source(path: Path, expected: str) -> str:
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected:
        raise ValueError('Source SHA-256 does not match the fixed protocol')
    return actual


def validate_stems(directory: Path, duration: float) -> dict:
    """Require the original HTDemucs frontend, including complete aligned stems."""
    import soundfile as sf
    result = {}
    for name in ['bass', 'drums', 'other', 'vocals']:
        path = directory / f'{name}.wav'
        if not path.is_file():
            raise ValueError(f'Missing stem: {name}')
        info = sf.info(path)
        if (info.samplerate != 44100 or info.channels != 2
                or abs(info.frames / info.samplerate - duration) > .001):
            raise ValueError(f'Invalid stem format or duration: {name}')
        result[name] = dict(sample_rate=info.samplerate, channels=info.channels, frames=info.frames,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if len({s['frames'] for s in result.values()}) != 1:
        raise ValueError('Stems do not share exact frame count')
    return result


def normalize_sections(raw: list[dict], duration: float) -> list[dict]:
    if not math.isfinite(duration) or duration <= 0 or not raw:
        raise ValueError('Nonempty sections and a finite positive duration are required')
    result = []

    def add(start, end, label, model_end=None, generated=False):
        result.append(dict(id=f'section-{len(result)+1}', start=start, end=end, label=label,
                           display_label=LABELS[label], review_status='unreviewed',
                           model_end=model_end, generated_gap=generated))

    cursor = 0.
    for section in raw:
        start, end, label = section.get('start'), section.get('end'), section.get('label')
        if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or not math.isfinite(start) or not math.isfinite(end) or start < 0
                or end <= start or start < cursor - 1e-7 or start >= duration
                or end > duration + .05 or label not in LABELS):
            raise ValueError('Invalid, overlapping, unordered, or unknown model section')
        if start > cursor + 1e-7:
            add(cursor, start, 'unknown', generated=True)
        start = max(start, cursor)
        bounded_end = min(end, duration)
        add(start, bounded_end, label, model_end=end)
        cursor = bounded_end
    if cursor < duration:
        add(cursor, duration, 'unknown', generated=True)
    return result


def summarize_candidate(raw: list[dict], duration: float) -> dict:
    sections = normalize_sections(raw, duration)
    unknown = sum(s['end'] - s['start'] for s in sections if s['label'] in ['unknown', 'start', 'end'])
    return dict(sections=sections, section_count=len(sections), coverage=1.,
                unresolved_seconds=unknown, semantic_quality='not_evaluated',
                reference_status='not_annotated', ready_as_default=False)


def render_review(candidates: list[dict]) -> str:
    template = Path(__file__).with_name('song_structure_review.html').read_text()
    return template.replace('__CANDIDATES__', json.dumps(candidates, ensure_ascii=False).replace('<', '\\u003c'))


def load_ready_candidate(directory: Path) -> dict:
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['status'] != 'candidate_ready_unreviewed':
        raise ValueError('Only completed inference runs can be published for review')
    source = manifest['source']
    verify_source(Path(source['audio']), source['audio_sha256'])
    candidate = json.loads((directory / 'candidate.json').read_text())
    expected = dict(title=source['title'], job=source['job'],
                    fingerprint=source['root_source']['fingerprint'],
                    source_start=source['root_source']['source_start'])
    duration = candidate.get('duration')
    if (any(candidate.get(k) != v for k, v in expected.items())
            or not isinstance(duration, (int, float)) or not math.isfinite(duration)
            or abs(duration - source['root_source']['duration']) > .05):
        raise ValueError('Candidate source does not match the completed run')
    # Revalidate intervals and keep quality claims conservative on the review page.
    normalized = normalize_sections(candidate['sections'], candidate['duration'])
    bounds = lambda sections: [(s['start'], s['end'], s['label']) for s in sections]
    if bounds(normalized) != bounds(candidate['sections']):
        raise ValueError('Published candidate must have canonical complete intervals')
    if (candidate.get('ready_as_default') is not False
            or candidate.get('semantic_quality') != 'not_evaluated'
            or any(s.get('review_status') != 'unreviewed' for s in candidate['sections'])):
        raise ValueError('Candidate review must not claim verified quality')
    return candidate
