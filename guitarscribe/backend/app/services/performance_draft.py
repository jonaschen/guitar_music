"""A reversible performance score; never mutate or simplify source harmony."""
from ..models.score import SongScore
from .chord_grid_candidate import build_chord_grid_candidate
from .voicings import ChordVoicingProvider


def build_performance_draft(score: SongScore):
    candidate = score.model_copy(deep=True)
    timing = {'changes': [], 'protected': [], 'unquantized_edges': []}
    grid_applied = False
    if (score.analysis.timing_status == 'metered' and score.analysis.time_signature == '4/4'
            and not score.provenance.parameters.get('chord_grid_candidate')):
        candidate, timing = build_chord_grid_candidate(score)
        grid_applied = True
    provider = ChordVoicingProvider()
    repaired, unresolved, manual = [], [], []
    for chord in candidate.chords:
        if chord.symbol.lower() in {'n', 'nc', 'n.c.', 'no_chord'}:
            continue
        selected = next((v for v in chord.available_voicings if v.id == chord.voicing_id),
                        chord.available_voicings[0] if chord.available_voicings else None)
        incomplete = selected is None or 'incomplete' in selected.tags
        if not incomplete:
            continue
        if chord.edited and selected is not None:
            manual.append(chord.id)
            unresolved.append(chord.id)
            continue
        if tuple(candidate.guitar.tuning) != (40, 45, 50, 55, 59, 64):
            unresolved.append(chord.id)
            continue
        voicings = provider.get(chord.shape_symbol or chord.symbol,
                                capo=candidate.analysis.capo, max_fret=candidate.guitar.max_fret)
        complete = [v for v in voicings if 'incomplete' not in v.tags]
        if complete:
            chord.available_voicings = complete
            chord.voicing_id = complete[0].id
            repaired.append(chord.id)
        else:
            unresolved.append(chord.id)
    candidate.provenance.parameters.update({
        'performance_draft': 'preserve-harmony-v1',
        'performance_voicings_repaired': len(repaired),
        'performance_voicings_unresolved': len(unresolved),
        'performance_timing_changes': len(timing['changes']),
        'performance_unquantized_edges': len(timing['unquantized_edges']),
    })
    return candidate, dict(grid_applied=grid_applied, timing=timing,
                          repaired_voicings=repaired, unresolved_voicings=unresolved,
                          protected_manual_voicings=manual,
                          chord_count_changed=False, symbols_changed=False, beats_changed=False,
                          applied=False, saved=False)
