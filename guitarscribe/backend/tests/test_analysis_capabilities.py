from pathlib import Path

from app.core.config import BeatEngine, ChordEngine, Settings
from app.services import capabilities
from app.core.pipeline import create_pipeline


def test_new_engine_is_not_advertised_when_only_vamp_host_is_installed(monkeypatch):
    monkeypatch.setattr(capabilities, 'module_available', lambda _: True)
    monkeypatch.setattr(capabilities, 'chordino_available', lambda: False)
    settings = Settings(beat_engine=BeatEngine.BEAT_THIS_SMALL, chord_engine=ChordEngine.AUTO)
    result = capabilities.analysis_capabilities(settings)
    assert result['improved_accompaniment'] is False
    assert result['chord_engine'] == 'chromagram'
    assert create_pipeline(settings).chord_analyzer.analyzer.__class__.__name__ == 'ChromagramChordAnalyzer'


def test_explicit_unavailable_chordino_fails_instead_of_using_old_engine(monkeypatch):
    import pytest
    monkeypatch.setattr(capabilities, 'chordino_available', lambda: False)
    with pytest.raises(RuntimeError, match='Chordino plugin'):
        create_pipeline(Settings(chord_engine=ChordEngine.CHORDINO))


def test_engine_pair_and_dependencies_are_required_for_improved_label(monkeypatch):
    monkeypatch.setattr(capabilities, 'chordino_available', lambda: True)
    monkeypatch.setattr(capabilities, 'module_available', lambda _: True)
    settings = Settings(beat_engine=BeatEngine.BEAT_THIS_SMALL, chord_engine=ChordEngine.CHORDINO)
    assert capabilities.analysis_capabilities(settings)['improved_accompaniment'] is True
    settings.beat_engine = BeatEngine.LIBROSA
    assert capabilities.analysis_capabilities(settings)['improved_accompaniment'] is False


def test_runtime_rhythm_directory_is_not_silently_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv('GUITARSCRIBE_RHYTHM_PATTERNS_DIR', str(tmp_path))
    assert Settings.from_env().rhythm_patterns_dir == Path(tmp_path)
