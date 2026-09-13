import soundfile as sf

from app.evaluation.diagnostic_audio import render_melody_diagnostic
from app.models.analysis import MelodyNote


def test_diagnostic_melody_render_has_expected_duration_and_audible_signal(tmp_path):
    output = tmp_path / "melody.wav"
    render_melody_diagnostic(
        [MelodyNote(id="c4", start=0.25, end=0.75, midi=60, note="C4", confidence=0.8)],
        duration_seconds=1.0,
        output_path=output,
    )

    audio, sample_rate = sf.read(output)
    assert sample_rate == 16000
    assert len(audio) == 16000
    assert max(abs(audio)) > 0.1
    assert max(abs(audio[:3000])) == 0
