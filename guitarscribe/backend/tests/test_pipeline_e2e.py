import pytest
from app.core.config import Settings, ChordEngine
from app.core.pipeline import create_pipeline
from app.models.audio import SourceRequest, SourceType

@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pipeline_e2e(sample_wav):
    settings = Settings(chord_engine=ChordEngine.CHROMAGRAM)
    pipeline = create_pipeline(settings)
    
    request = SourceRequest(
        source_type=SourceType.LOCAL,
        path=sample_wav,
        rights_confirmed=True
    )
    
    score = await pipeline.run(request, {"chord_complexity": "standard"})
    
    assert score.schema_version == "1.0"
    assert len(score.chords) > 0
    assert len(score.beats) > 0
    assert 60 <= score.analysis.bpm <= 200
    
    json_str = score.model_dump_json()
    assert isinstance(json_str, str)
    assert len(json_str) > 0
