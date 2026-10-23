"""Standalone local annotation service. Never writes score or revision databases."""
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .lyric_anchor_audit import audit_anchors


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor_index: int = Field(ge=0)
    raw_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    reviewed: bool = False
    skipped: bool = False


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_id: str = Field(max_length=64)
    observations: list[Observation] = Field(min_length=1, max_length=100)


def create_capture_app(packet: Path, receipts: Path) -> FastAPI:
    config = json.loads((packet / 'config.json').read_text())
    score = json.loads((packet / 'score.json').read_text())
    manifest = json.loads((packet / 'manifest.json').read_text())
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get('/')
    def index():
        return FileResponse(packet / 'index.html', headers={'Cache-Control':'no-store'})

    @app.get('/config')
    def get_config():
        return config

    @app.get('/audio.wav')
    def audio():
        return FileResponse(packet / 'audio.wav', media_type='audio/wav')

    @app.post('/marks')
    def mark(payload: Submission):
        if payload.config_id != config['config_id']:
            raise HTTPException(409, 'Annotation source changed; reload before marking')
        seen = set()
        for obs in payload.observations:
            if obs.anchor_index >= len(config['anchors']) or obs.anchor_index in seen:
                raise HTTPException(422, 'Invalid or duplicate lyric anchor')
            seen.add(obs.anchor_index)
            if obs.skipped:
                if obs.raw_seconds is not None or obs.seconds is not None:
                    raise HTTPException(422, 'Skipped anchors must not invent timestamps')
            elif obs.raw_seconds is None or obs.seconds is None:
                raise HTTPException(422, 'A marked anchor needs both original and current time')
            for time in (obs.raw_seconds, obs.seconds):
                if time is not None and (not math.isfinite(time) or time > config['content_duration']):
                    raise HTTPException(422, 'Marker falls outside source content')
        if all(obs.skipped for obs in payload.observations):
            raise HTTPException(422, 'At least one timed observation is needed')
        observations = [obs.model_dump() for obs in payload.observations]
        result = audit_anchors(score, manifest, observations, config['analysis_start'])
        receipt_id = uuid4().hex
        record = {
            'receipt_id': receipt_id, 'received_utc': datetime.now(timezone.utc).isoformat(),
            'config_id': config['config_id'], 'revision': config['revision'],
            'audio_sha256': config['audio_sha256'], 'analysis_start': config['analysis_start'],
            'anchors': config['anchors'], 'observations': observations, 'audit': result,
            'interpretation': 'User landmarks with unknown reaction latency. Not automatic beat/chord truth.',
        }
        receipts.mkdir(parents=True, exist_ok=True)
        # Every submission is a new receipt; never overwrite a previous listening record.
        with (receipts / f'{receipt_id}.json').open('x') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
        return {'receipt_id': receipt_id}

    return app
