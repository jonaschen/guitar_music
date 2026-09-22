import pytest
from pydantic import ValidationError

from app.core.config import ChordEngine, Settings
from app.core.pipeline import create_pipeline


def test_chord_decoder_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("GUITARSCRIBE_CHORD_ENGINE", "chromagram")
    monkeypatch.setenv("GUITARSCRIBE_CHORD_CHANGE_THRESHOLD", "0.2")
    monkeypatch.setenv("GUITARSCRIBE_CHORD_NO_CHORD_THRESHOLD", "0.24")
    monkeypatch.setenv("GUITARSCRIBE_CHORD_TONAL_PRIOR_SCALE", "0.5")

    settings = Settings.from_env()
    pipeline = create_pipeline(settings)
    config = pipeline.chord_analyzer.analyzer.decoder_config

    assert settings.chord_engine == ChordEngine.CHROMAGRAM
    assert config.change_threshold == 0.2
    assert config.no_chord_threshold == 0.24
    assert config.tonal_prior_scale == 0.5


def test_chord_decoder_settings_reject_out_of_range_values():
    with pytest.raises(ValidationError):
        Settings(chord_change_threshold=-0.1)
