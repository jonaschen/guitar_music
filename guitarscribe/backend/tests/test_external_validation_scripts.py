import hashlib
import json

import numpy as np
import pytest
import soundfile as sf

from app.evaluation.annotations import QualityAnnotation
from scripts.prepare_external_validation import run as prepare
from scripts.evaluate_external_validation import run as evaluate


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_local_packet_and_saved_result_evaluation_preserve_source_and_refuse_tampering(tmp_path):
    # Contract fixture only, not a service response or recognition experiment.
    audio = tmp_path / "source.wav"
    sf.write(audio, np.zeros(20*8000), 8000)
    source_hash = digest(audio)
    ann = QualityAnnotation(recording_id="fixture", source_sha256=source_hash, source_file=audio.name,
                            rights_note="Synthetic silence fixture", difficulty="easy",
                            excerpt_start=0, excerpt_end=20,
                            beats=[{"time": i*.5} for i in range(40)],
                            downbeats=[{"time": i*2} for i in range(10)],
                            chords=[{"start": 0, "end": 20, "label": "N"}])
    ref = tmp_path / "reference.json"
    ref.write_text(ann.model_dump_json())
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"cases": [{"audio": {"path": audio.name, "sha256": source_hash},
                                           "annotation": {"path": ref.name, "sha256": digest(ref)}}]}))
    packet = tmp_path / "packet"
    prepare(tmp_path, plan, packet)
    manifest = json.loads((packet / "manifest.json").read_text())
    assert manifest["uploaded"] is False
    assert sf.info(packet / "fixture.wav").duration == 15
    assert digest(audio) == source_hash
    results = tmp_path / "results"
    results.mkdir()
    (results / "fixture.beats.json").write_text(json.dumps([[i*.5, i%4+1] for i in range(30)]))
    (results / "fixture.chords.json").write_text(json.dumps([[0, 15, "N"]]))
    output = tmp_path / "report.json"
    evaluate(packet, results, output)
    report = json.loads(output.read_text())
    assert report["external_output_is_ground_truth"] is False
    assert report["recordings"][0]["timing"]["beat_f_measure"] == 1
    with pytest.raises(FileExistsError):
        evaluate(packet, results, output)
    with pytest.raises(FileExistsError):
        prepare(tmp_path, plan, packet)
    (packet / "fixture.reference.json").write_text("{}")
    with pytest.raises(ValueError, match="packet has changed"):
        evaluate(packet, results, tmp_path / "tampered.json")
    assert not (tmp_path / "tampered.json").exists()
