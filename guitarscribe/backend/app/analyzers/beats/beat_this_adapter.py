"""Optional learned beat/downbeat engine; loaded only when explicitly selected."""
import hashlib
from importlib.metadata import version
from pathlib import Path

from ...models.audio import NormalizedAudio
from .learned_projection import project_learned_beats
from ..worker import run_blocking_analysis


class BeatThisBeatAnalyzer:
    def __init__(self, predictor=None):
        self._predictor=predictor
        self._version='injected' if predictor is not None else 'not-loaded'
        self.parameters={'beat_this_checkpoint':'small0','beat_this_device':'cpu','beat_this_dbn':False}

    def _load(self):
        if self._predictor is None:
            try:
                import torch
                from beat_this.inference import File2Beats
            except ImportError as error:
                raise RuntimeError('Beat This requires the optional timing dependencies; install CPU torch/torchaudio and guitarscribe[timing].') from error
            self._predictor=File2Beats(checkpoint_path='small0',device='cpu',dbn=False)
            self._version=version('beat-this')
            checkpoint=Path(torch.hub.get_dir())/'checkpoints/beat_this-small0.ckpt'
            if checkpoint.exists():
                self.parameters['beat_this_weights_sha256']=hashlib.sha256(checkpoint.read_bytes()).hexdigest()

    async def analyze(self,audio:NormalizedAudio):
        return await run_blocking_analysis(self._analyze, audio)

    def _analyze(self,audio:NormalizedAudio):
        self._load()
        beats,downbeats=self._predictor(str(audio.path))
        return project_learned_beats([float(t)for t in beats],[float(t)for t in downbeats],self._version)
