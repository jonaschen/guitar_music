"""Lossless frame-pitch sidecar, separate from notation-oriented MelodyNote.

This experimental representation does not imply a recognized melody. Null
frequency means silence; probability is source evidence, not note accuracy.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MelodyContour(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0"] = "1.0"
    playback_kind: Literal["frame_hold_continuous_phase"] = "frame_hold_continuous_phase"
    status: Literal["experimental"] = "experimental"
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_start: float = Field(ge=0)
    source_end: float = Field(gt=0)
    hop_seconds: float = Field(gt=0)
    frequencies_hz: tuple[float | None, ...]
    voiced_probabilities: tuple[float | None, ...]

    @model_validator(mode="after")
    def validate_frames(self):
        if self.source_end <= self.source_start or not self.frequencies_hz:
            raise ValueError("Contour must have frames and positive source duration")
        if len(self.frequencies_hz) != len(self.voiced_probabilities):
            raise ValueError("Frame and probability counts differ")
        if any(hz is not None and hz <= 0 for hz in self.frequencies_hz):
            raise ValueError("Frequency must be positive, or null for silence")
        if any(p is not None and not 0 <= p <= 1 for p in self.voiced_probabilities):
            raise ValueError("Probability must be in [0, 1], or null")
        duration = self.source_end - self.source_start
        if not ((len(self.frequencies_hz) - 1) * self.hop_seconds < duration + 1e-8
                and len(self.frequencies_hz) * self.hop_seconds >= duration - 1e-8):
            raise ValueError("Frame count does not cover the recorded source duration")
        return self
