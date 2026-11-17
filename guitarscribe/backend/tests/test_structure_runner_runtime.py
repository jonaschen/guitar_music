import hashlib
from pathlib import Path
import pytest
from scripts.analyze_song_structure import configured_model_cache


def test_configured_cache_requires_existing_verified_weights_before_inference(tmp_path):
    cache = tmp_path/'cache'; cache.mkdir()
    checkpoint = cache/'fold.pth';checkpoint.write_bytes(b'pinned model')
    protocol = {'model_cache':str(cache),'runtime_weights':[{'path':str(checkpoint),'sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest()}]}
    assert configured_model_cache(protocol,tmp_path/'fallback') == cache
    checkpoint.write_bytes(b'changed')
    with pytest.raises(ValueError,match='SHA-256'): configured_model_cache(protocol,tmp_path/'fallback')
    checkpoint.unlink()
    with pytest.raises(FileNotFoundError): configured_model_cache(protocol,tmp_path/'fallback')


def test_legacy_protocol_retains_its_original_per_experiment_cache(tmp_path):
    assert configured_model_cache({},tmp_path/'original') == tmp_path/'original'
