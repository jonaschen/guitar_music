"""Manual meter defines intervals; cached observations only suggest dyadic exceptions."""
import math
from pydantic import BaseModel, ConfigDict, Field


class PracticeGrid(BaseModel):
    model_config = ConfigDict(extra='forbid')
    bpm: float = Field(ge=20, le=300, allow_inf_nan=False)
    beats: int = Field(ge=1, le=12, strict=True)
    anchor: float = Field(ge=0, allow_inf_nan=False)


def bars(grid, duration):
    length = 60 / grid.bpm * grid.beats
    first = math.floor(-grid.anchor / length + 1e-9)
    last = math.ceil((duration - grid.anchor) / length - 1e-9)
    if last - first > 6000:
        raise ValueError('小節數超過6000，請縮短來源範圍或調整拍數。')
    return [(grid.anchor + i * length, grid.anchor + (i + 1) * length) for i in range(first, last)]


def grid_aligned(segments, grid, duration):
    if grid.anchor > duration:
        return False
    length = 60 / grid.bpm * grid.beats
    for s in segments:
        i = math.floor(((s.start + s.end) / 2 - grid.anchor) / length + 1e-9)
        a = grid.anchor + i * length
        found = False
        for divisor in (1, 2, 4):
            if grid.beats % divisor:
                continue
            for part in range(divisor):
                x, y = max(0, a + part * length / divisor), min(duration, a + (part + 1) * length / divisor)
                if abs(s.start - x) < 1e-7 and abs(s.end - y) < 1e-7:
                    found = True
        if not found:
            return False
    return True


def stable_root(frames, start, end):
    """Uncalibrated conservative clue, not probability or a ground-truth root."""
    if end <= start:
        return None
    total = [0.] * 12
    covered = no_chord = 0.
    support = [0.] * 12
    for row in frames:
        weight = max(0., min(end, row[1]) - max(start, row[0]))
        if not weight:
            continue
        scores = row[2:14]
        order = sorted(range(12), key=lambda p: -scores[p])
        covered += weight
        no_chord += weight * row[14]
        for p in range(12):
            total[p] += weight * scores[p]
        winner = order[0]
        if scores[winner] > 0 and scores[winner] >= 1.5 * scores[order[1]] and scores[winner] > row[14]:
            support[winner] += weight
    order = sorted(range(12), key=lambda p: -total[p])
    winner = order[0]
    if covered < .8 * (end - start) or total[winner] <= no_chord or total[winner] <= 0 or total[winner] < 1.5 * total[order[1]] or support[winner] < .7 * (end - start):
        return None
    return winner


def transfer(previous, start, end):
    overlaps = [s for s in previous if s['start'] < end - 1e-8 and s['end'] > start + 1e-8]
    confirmed = [s for s in overlaps if s['status'] == 'confirmed']
    roots = {s['root'] for s in confirmed}
    coverage = sum(max(0., min(end, s['end']) - max(start, s['start'])) for s in confirmed)
    root = next(iter(roots)) if len(roots) == 1 and coverage >= end - start - 1e-7 else None
    originals = {s['original_root'] for s in overlaps}
    return dict(original_root=next(iter(originals)) if len(originals) == 1 else None,
                root=root, status='confirmed' if root is not None else 'unsure' if confirmed else 'pending')


def segmentation_plan(document, grid, evidence=None):
    duration = document['source']['duration']
    if grid.anchor > duration:
        raise ValueError('對齊點超出歌曲。')
    frames = evidence['frames'] if evidence else []
    spans = bars(grid, duration)
    segments, exceptions = [], []
    frame_index = 0
    for number, (raw_start, raw_end) in enumerate(spans, 1):
        start, end = max(0., raw_start), min(duration, raw_end)
        while frame_index < len(frames) and frames[frame_index][1] <= start:
            frame_index += 1
        stop = frame_index
        while stop < len(frames) and frames[stop][0] < end:
            stop += 1
        window = frames[frame_index:stop]
        cuts = [start, end]
        # File edges are clipped bars, never extrapolate missing observations.
        if raw_start >= -1e-8 and raw_end <= duration + 1e-8 and grid.beats % 2 == 0:
            mid = (raw_start + raw_end) / 2
            left, right = stable_root(window, start, mid), stable_root(window, mid, end)
            quarter_cuts = []
            if grid.beats % 4 == 0:
                for a, b in ((start, mid), (mid, end)):
                    q = (a + b) / 2
                    r1, r2 = stable_root(window, a, q), stable_root(window, q, b)
                    if r1 is not None and r2 is not None and r1 != r2:
                        quarter_cuts.append(q)
            if quarter_cuts or (left is not None and right is not None and left != right):
                cuts = sorted([start, mid, *quarter_cuts, end])
                exceptions.append({'bar': number, 'start': start, 'end': end, 'parts': len(cuts) - 1})
        for a, b in zip(cuts, cuts[1:]):
            segments.append(dict(id=f'grid-{len(segments)}', start=a, end=b, **transfer(document['segments'], a, b)))
    if len(segments) > 6000:
        raise ValueError('分段超過6000，請縮短來源範圍。')
    result = dict(schema_version=2, source=document['source'], grid=grid.model_dump(mode='json'), segments=segments)
    review = [{'start': s['start'], 'end': s['end'], 'roots': sorted({old['root'] for old in document['segments'] if old['status'] == 'confirmed' and old['start'] < s['end'] - 1e-8 and old['end'] > s['start'] + 1e-8})} for s in segments if s['status'] == 'unsure']
    return dict(document=result, bars=len(spans), exceptions=exceptions, review=review,
                preserved=sum(s['status'] == 'confirmed' for s in segments), evidence_available=evidence is not None,
                method='metrical-root-changes-v1', note='自動細分是未驗證的換根音線索；無明確線索時保留一小節一段。')
