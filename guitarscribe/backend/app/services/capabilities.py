"""Describe available engines without starting inference or downloading models."""
from importlib.util import find_spec
import shutil

from ..core.config import BeatEngine, ChordEngine, Settings


def module_available(name: str) -> bool:
    try:
        return find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def chordino_available() -> bool:
    try:
        import vamp
        return 'nnls-chroma:chordino' in vamp.list_plugins()
    except Exception:
        return False


def analysis_capabilities(settings: Settings) -> dict:
    chordino = chordino_available()
    learned = all(module_available(name) for name in ('beat_this', 'torch', 'torchaudio'))
    actual_chord = (ChordEngine.CHORDINO.value if chordino else ChordEngine.CHROMAGRAM.value
                    ) if settings.chord_engine == ChordEngine.AUTO else settings.chord_engine.value
    separator = settings.melody_separator == 'demucs' and bool(
        shutil.which(settings.demucs_binary or 'demucs'))
    melody = (module_available('basic_pitch') and any(module_available(n) for n in ('onnxruntime', 'tensorflow'))
              ) or separator
    return {
        'beat_engine': settings.beat_engine.value,
        'chord_engine': actual_chord,
        'improved_accompaniment': settings.beat_engine == BeatEngine.BEAT_THIS_SMALL
            and learned and actual_chord == ChordEngine.CHORDINO.value and chordino,
        'youtube_enabled': settings.youtube_enabled and bool(shutil.which(settings.youtube_dl_binary)),
        'vocal_separation_enabled': separator,
        'melody_available': melody,
        'recommended_analysis_seconds': 45,
    }
