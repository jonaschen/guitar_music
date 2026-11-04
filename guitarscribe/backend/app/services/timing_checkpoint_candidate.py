"""Create an explicit timing-only copy from a completed offline comparison."""
import hashlib
import json

from ..evaluation.timing_quality import timing_quality
from ..models.analysis import BeatInfo
from ..models.score import SongScore


def build_checkpoint_candidate(score: SongScore, report: dict) -> SongScore:
    """Require a matching source and full engineering pass; do not change chords.

    Source bytes are checked by the caller against the frozen report before this
    pure builder is used. It is deliberately not a default analyzer fallback.
    """
    case = report['case']
    if report['checkpoint'] != 'final0' or not report.get('weights_sha256'):
        raise ValueError('Requires the fixed final0 comparison')
    if (score.song.duration_seconds != case['duration'] or score.song.source_url != case['source_url']
            or score.song.source_start_seconds != 0):
        raise ValueError('Comparison source does not match this score')
    decoder = report.get('selected_decoder','dbn')
    if decoder not in ('dbn','continuity'):
        raise ValueError('Unknown fixed comparison decoder')
    observation = report['decoders'][decoder]
    # Recompute; never trust a stored boolean or a stored projection.
    quality = timing_quality(observation['beats'], observation['downbeats'], case['duration'], report['beat_this'])
    if not quality['engineering_pass']:
        raise ValueError('Candidate has unresolved timing structure or density')
    if score.analysis.timing_status != 'unmetered':
        raise ValueError('Keep the existing metered score; do not replace it automatically')
    candidate = score.model_copy(deep=True)
    projected = quality['projection']
    candidate.beats = [BeatInfo.model_validate(b) for b in projected['beats']]
    candidate.analysis.timing_status = 'metered'
    candidate.analysis.bpm = projected['bpm']
    candidate.analysis.time_signature = projected['time_signature']
    candidate.analysis.warnings.append('拍格試驗稿：通過工程檢查，尚待試聽；原稿保留，和弦時間未改。')
    candidate.provenance.beat_engine = 'beat-this'
    candidate.provenance.beat_engine_version = report['beat_this']
    candidate.provenance.tempo_map_version = f'experimental-final0-{decoder}-v1'
    candidate.provenance.parameters.update(
        candidate_source_job_id=case['job'], beat_this_checkpoint='final0', beat_this_dbn=True,
        beat_this_weights_sha256=report['weights_sha256'],
        timing_candidate=f'final0-{decoder}-fixed-v1', timing_candidate_confirmed=False,
        timing_candidate_source_sha256=case['source_sha256'],
        timing_candidate_base_sha256=hashlib.sha256(score.model_dump_json().encode()).hexdigest())
    if decoder=='continuity':
        candidate.provenance.parameters['tempo_continuity_reference']=json.dumps(report['reference'],sort_keys=True)
    # A time-table rhythm has no metered pattern. Keep it intact in this timing
    # copy; a listening renderer chooses its rhythm separately and records it.
    assert candidate.chords == score.chords and candidate.melody == score.melody
    return candidate
