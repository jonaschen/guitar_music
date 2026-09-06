import pytest
from pathlib import Path
import shutil
from types import SimpleNamespace
from app.analyzers.preprocessor import DemucsMelodySeparator, FFmpegPreprocessor
from app.models.audio import AudioAsset, NormalizedAudio, SourceType
from app.models.analysis import MelodyMode

@pytest.mark.asyncio
async def test_normalize_valid(sample_wav):
    preprocessor = FFmpegPreprocessor()
    asset = AudioAsset(path=sample_wav, source_type=SourceType.LOCAL)
    
    normalized = await preprocessor.normalize(asset)
    
    assert normalized.sample_rate == 44100
    assert normalized.channels == 1
    assert normalized.bit_depth == 16
    assert abs(normalized.duration_seconds - 8.0) < 0.1
    assert normalized.path.exists()

@pytest.mark.asyncio
async def test_normalize_missing_file(tmp_path):
    preprocessor = FFmpegPreprocessor()
    asset = AudioAsset(path=tmp_path / "nonexistent.wav", source_type=SourceType.LOCAL)
    
    with pytest.raises(RuntimeError):
        await preprocessor.normalize(asset)


@pytest.mark.asyncio
async def test_demucs_separator_uses_generated_vocal_stem(sample_wav, monkeypatch):
    def fake_run(cmd, capture_output, timeout):
        output_dir = Path(cmd[cmd.index("--out") + 1])
        stem = output_dir / "htdemucs" / "test" / "vocals.wav"
        stem.parent.mkdir(parents=True)
        shutil.copyfile(sample_wav, stem)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr("app.analyzers.preprocessor.subprocess.run", fake_run)
    separator = DemucsMelodySeparator(binary="/usr/local/bin/demucs")
    audio = NormalizedAudio(path=sample_wav, duration_seconds=8.0)

    separated, did_separate = await separator.separate(audio, MelodyMode.VOCAL)

    assert did_separate is True
    assert separated.path.name == "vocals.wav"
    assert separated.duration_seconds == pytest.approx(8.0, abs=0.1)


@pytest.mark.asyncio
async def test_demucs_separator_leaves_non_vocal_mode_unchanged(sample_wav):
    separator = DemucsMelodySeparator(binary="/missing/demucs")
    audio = NormalizedAudio(path=sample_wav, duration_seconds=8.0)

    separated, did_separate = await separator.separate(audio, MelodyMode.GUITAR)

    assert separated is audio
    assert did_separate is False
