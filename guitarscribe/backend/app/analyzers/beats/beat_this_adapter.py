"""Optional learned beat/downbeat engine; loaded only when explicitly selected."""
import hashlib
from importlib.metadata import version
from pathlib import Path

from ...models.audio import NormalizedAudio
from .learned_projection import project_learned_beats
from .timing_diagnostics import BeatProjectionError, describe_observations
from .guarded_recovery import check_recovery, POLICY
from ..worker import run_blocking_analysis


class BeatThisBeatAnalyzer:
    def __init__(self, predictor=None, *, recovery_enabled=False, frame_predictor=None,
                 primary_decoder=None, recovery_decoder=None):
        self._predictor=predictor
        self._frame_predictor=frame_predictor
        self._primary_decoder=primary_decoder
        self._recovery_decoder=recovery_decoder
        self.recovery_enabled=recovery_enabled
        self.recovery_report=None
        self._version='injected' if predictor is not None or frame_predictor is not None else 'not-loaded'
        self.parameters={'beat_this_checkpoint':'small0','beat_this_device':'cpu','beat_this_dbn':False}

    def _load(self):
        if self._predictor is None and self._frame_predictor is None:
            try:
                import torch
                from beat_this.inference import File2Beats
            except ImportError as error:
                raise RuntimeError('Beat This requires the optional timing dependencies; install CPU torch/torchaudio and guitarscribe[timing].') from error
            if self.recovery_enabled:
                from beat_this.inference import Audio2Frames
                from beat_this.preprocessing import load_audio
                from beat_this.model.postprocessor import Postprocessor
                frames = Audio2Frames(checkpoint_path='small0',device='cpu',float16=False)
                self._frame_predictor=lambda path: frames(*load_audio(path))
                self._primary_decoder=Postprocessor('minimal')
            else:
                self._predictor=File2Beats(checkpoint_path='small0',device='cpu',dbn=False)
            self._version=version('beat-this')
            checkpoint=Path(torch.hub.get_dir())/'checkpoints/beat_this-small0.ckpt'
            if checkpoint.exists():
                self.parameters['beat_this_weights_sha256']=hashlib.sha256(checkpoint.read_bytes()).hexdigest()

    async def analyze(self,audio:NormalizedAudio):
        return await run_blocking_analysis(self._analyze, audio)

    def _analyze(self,audio:NormalizedAudio):
        self._load()
        self.recovery_report=None
        self.parameters['beat_this_dbn']=False
        if self.recovery_enabled:
            self.parameters.update(beat_recovery_policy=POLICY,beat_recovery_status='primary_retained')
        frames = self._frame_predictor(str(audio.path)) if self._frame_predictor is not None else None
        beats,downbeats = self._primary_decoder(*frames) if frames is not None else self._predictor(str(audio.path))
        beats, downbeats = [float(t) for t in beats], [float(t) for t in downbeats]
        try:
            return project_learned_beats(beats, downbeats, self._version)
        except ValueError as error:
            evidence = describe_observations(beats, downbeats)
            if self.recovery_enabled and frames is not None:
                try:
                    if self._recovery_decoder is None:
                        from beat_this.model.postprocessor import Postprocessor
                        self._recovery_decoder=Postprocessor('dbn')
                    recovered_beats,recovered_downbeats=([float(t) for t in values] for values in self._recovery_decoder(*frames))
                    recovered,report=check_recovery(beats,downbeats,recovered_beats,recovered_downbeats,
                                                    audio.duration_seconds,self._version)
                    report.update(primary=dict(evidence),candidate=describe_observations(recovered_beats,recovered_downbeats),
                                  primary_rejection_reason=str(error),
                                  decoder_parameters=dict(beats_per_bar=[3,4],min_bpm=55,max_bpm=215,fps=50,transition_lambda=100))
                    self.recovery_report=report
                    self.parameters['beat_recovery_status']='recovered' if recovered is not None else 'rejected'
                    if recovered is not None:
                        self.parameters['beat_this_dbn']=True
                        recovered.warnings.append('拍格使用固定解碼與結構保護恢復；不代表音樂正確性已經驗證。')
                        return recovered
                except Exception as recovery_error:
                    # Optional decoding must not lose an otherwise useful chord analysis.
                    self.recovery_report=dict(policy=POLICY,eligible=False,reasons=['decoder_unavailable_or_failed'],
                                              error=str(recovery_error),primary=dict(evidence),musical_verdict='unconfirmed')
                    self.parameters['beat_recovery_status']='unavailable'
                evidence['recovery']=self.recovery_report
            evidence.update(engine='beat-this', engine_version=self._version,
                            parameters=dict(self.parameters), rejection_reason=str(error))
            raise BeatProjectionError(str(error), evidence) from error
