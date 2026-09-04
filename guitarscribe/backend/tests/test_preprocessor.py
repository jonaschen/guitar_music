import pytest
from pathlib import Path
from app.analyzers.preprocessor import FFmpegPreprocessor
from app.models.audio import AudioAsset, SourceType

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
