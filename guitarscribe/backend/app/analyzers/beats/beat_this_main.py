"""Opt-in recovery: preserve the current engine; use one fixed main-model policy.

The live default remains small0. Engineering checks do not certify musical time.
"""
import hashlib
from importlib.metadata import version
from pathlib import Path

from ...evaluation.timing_quality import timing_quality
from ...models.analysis import BeatAnalysis
from .timing_diagnostics import BeatProjectionError
from ..worker import run_blocking_analysis


class BeatThisMainAnalyzer:
    def __init__(self, predictor=None, *, primary=None, frame_predictor=None,
                 decoder=None):
        self.primary = primary
        self._predictor = predictor
        self._frames = frame_predictor
        self._decoder = decoder
        self._version = 'injected' if predictor is not None or frame_predictor is not None else 'not-loaded'
        self._model_parameters = dict(beat_this_checkpoint='final0', beat_this_device='cpu',
            beat_this_dbn=True, beat_quality_policy='fixed-main-dbn-v2')
        self.parameters = dict(self._model_parameters)
        self.recovery_report = None

    def _load(self):
        if self._predictor is not None or self._frames is not None:
            return
        try:
            import torch
            from beat_this.inference import Audio2Frames
            from beat_this.preprocessing import load_audio
            from beat_this.model.postprocessor import Postprocessor
            frames = Audio2Frames(checkpoint_path='final0', device='cpu', float16=False)
            self._frames = lambda path: frames(*load_audio(path))
            self._decoder = Postprocessor('dbn')
        except ImportError as error:
            raise RuntimeError('Main beat engine requires Beat This and the optional DBN dependencies.') from error
        self._version = version('beat-this')
        checkpoint = Path(torch.hub.get_dir())/'checkpoints/beat_this-final0.ckpt'
        self._model_parameters['beat_this_weights_sha256'] = hashlib.sha256(checkpoint.read_bytes()).hexdigest()

    async def analyze(self, audio):
        self.recovery_report = None
        prior = None
        if self.primary is not None:
            try:
                result = await self.primary.analyze(audio)
            except BeatProjectionError as error:
                prior = error.evidence
            else:
                self.parameters = dict(self.primary.parameters)
                self.recovery_report = self.primary.recovery_report
                return result
        try:
            result = await run_blocking_analysis(self._analyze, audio)
        except Exception as error:
            if prior is None:
                raise
            self.parameters = dict(self.primary.parameters)
            self.parameters['main_recovery_status'] = 'rejected'
            self.recovery_report = dict(primary=prior, main=self.recovery_report,
                error=str(error), policy='fixed-main-dbn-v2', eligible=False)
            evidence = dict(prior, main_recovery=self.recovery_report)
            raise BeatProjectionError('Main recovery did not confirm timing', evidence) from error
        if prior is not None:
            self.recovery_report['previous_rejection'] = prior
        return result

    def _analyze(self, audio):
        self._load()
        self.parameters = dict(self._model_parameters)
        frames = self._frames(str(audio.path)) if self._frames is not None else None
        raw = self._decoder(*frames) if frames is not None else self._predictor(str(audio.path))
        beats, downbeats = ([float(t) for t in values] for values in raw)
        base = timing_quality(beats, downbeats, audio.duration_seconds, self._version)
        report = base
        # 2026-11-05 human review rejected duration-majority tempo recovery:
        # a structurally stable grid still had half speed and a wrong first beat.
        # Keep that experiment offline; never retry it in the product pipeline.
        selected = 'dbn'
        self.recovery_report = dict(policy='fixed-main-dbn-v2', primary=base,
            candidate=report, selected_decoder=selected,
            continuity_status='disabled_after_human_rejection',
            eligible=report['engineering_pass'], musical_verdict='unconfirmed')
        self.parameters.update(beat_quality_status='passed' if report['engineering_pass'] else 'rejected',
                               main_recovery_decoder=selected)
        if not report['engineering_pass']:
            reason = 'Unconfirmed beat density or meter: '+', '.join(report['issues'])
            evidence = dict(report, engine='beat-this', engine_version=self._version,
                parameters=dict(self.parameters), rejection_reason=reason)
            raise BeatProjectionError(reason, evidence)
        result = BeatAnalysis.model_validate(report['projection'])
        result.warnings.append('完整版拍點恢復；工程檢查不等於音樂正確性驗收。')
        return result
