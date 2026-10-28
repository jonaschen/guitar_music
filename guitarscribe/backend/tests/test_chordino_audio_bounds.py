"""Vamp can emit an N marker beyond the end of a cropped audio buffer."""
import pytest
from app.analyzers.chords.chordino import decode_chord_events


@pytest.mark.parametrize('start,symbol', [(42.771156462, 'F'), (44.628752834, 'Bb')])
def test_real_45_second_crop_tail_does_not_extend_into_padding(start, symbol):
    events = decode_chord_events([
        {'timestamp': start, 'label': symbol},
        {'timestamp': 45.139591836, 'label': 'N'},
    ], 45)
    assert [(e.start, e.end, e.symbol) for e in events] == [(start, 45, symbol)]


def test_preserves_internal_boundaries_and_rest_while_removing_padding_events():
    events = decode_chord_events([
        {'timestamp': -.02, 'label': 'C'},
        {'timestamp': 1.25, 'label': 'N'},
        {'timestamp': 2.3, 'label': 'G'},
        {'timestamp': 4, 'label': 'Am'},
        {'timestamp': 4.1, 'label': 'F'},
    ], 4)
    assert [(e.id, e.start, e.end, e.symbol) for e in events] == [
        ('chord-1', 0, 1.25, 'C'), ('chord-3', 2.3, 4, 'G')]


def test_last_chord_ends_at_audio_without_terminal_marker():
    events = decode_chord_events([{'timestamp': .2, 'label': 'C'}], 3)
    assert (events[0].start, events[0].end) == (.2, 3)
