import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from .core.config import Settings
from .core.pipeline import AnalysisPipeline, create_pipeline
from .models.audio import SourceRequest, SourceType
from .models.analysis import AccidentalPreference
from .models.jobs import AnalysisJob
from .models.analysis import ChordVoicing
from .services.voicings import ChordVoicingProvider
from .services.capo import CapoAdvisor, CapoRecommendation
from .services.voicing_optimizer import SongVoicingOptimizer
from .services.lyrics import import_lrc, import_text
from .models.score import SongScore
from .services.jobs import AnalysisJobService, JobStore
from .exporters.chordpro import ChordProExporter
from .exporters.lrc import export_lrc
from .exporters.midi import export_midi
from .exporters.musicxml import export_musicxml
from .services.revisions import RevisionStore
from .services.transposition import TranspositionService


class TransposeScoreRequest(BaseModel):
    score: SongScore
    semitones: int = Field(default=0, ge=-11, le=11)
    accidental_preference: AccidentalPreference = AccidentalPreference.AUTO
    capo: int | None = Field(default=None, ge=0, le=12)


class HealthResponse(BaseModel):
    status: str = "ok"


class SaveRevisionRequest(BaseModel):
    score: SongScore
    revision_id: str | None = None


class SaveRevisionResponse(BaseModel):
    revision_id: str


app = FastAPI(
    title="GuitarScribe API",
    version="0.2.0",
    description="Audio analysis, editable scores, and local background analysis jobs.",
)
transposition_service = TranspositionService()
_job_service: AnalysisJobService | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_pipeline() -> AnalysisPipeline:
    return create_pipeline(Settings.from_env())


def get_revision_store() -> RevisionStore:
    settings = Settings.from_env()
    return RevisionStore(settings.work_dir / "revisions")


def get_job_service() -> AnalysisJobService:
    global _job_service
    if _job_service is None:
        settings = Settings.from_env()
        _job_service = AnalysisJobService(
            JobStore(settings.work_dir / "jobs"),
            pipeline_factory=lambda: create_pipeline(settings),
            max_concurrent_jobs=settings.max_concurrent_jobs,
            job_ttl_seconds=settings.job_ttl_seconds,
        )
    return _job_service


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/scores/transpose", response_model=SongScore)
async def transpose_score(request: TransposeScoreRequest) -> SongScore:
    return transposition_service.transpose_score(
        score=request.score,
        semitones=request.semitones,
        accidental_preference=request.accidental_preference,
        capo=request.capo,
    )


@app.post("/api/v1/jobs", response_model=AnalysisJob, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis_job(
    audio_file: UploadFile = File(...),
    rights_confirmed: bool = Form(...),
    melody_mode: str = Form(default="vocal"),
    chord_complexity: str = Form(default="standard"),
    job_service: AnalysisJobService = Depends(get_job_service),
) -> AnalysisJob:
    """Queue a local upload for analysis and return immediately."""
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Rights must be confirmed")
    content = await audio_file.read()
    if len(content) > Settings.from_env().max_upload_bytes:
        raise HTTPException(status_code=413, detail="Audio upload exceeds the configured size limit")
    return await job_service.submit(
        filename=audio_file.filename or "upload.wav",
        content=content,
        melody_mode=melody_mode,
        chord_complexity=chord_complexity,
    )


@app.get("/api/v1/jobs/{job_id}", response_model=AnalysisJob)
async def get_analysis_job(
    job_id: str,
    job_service: AnalysisJobService = Depends(get_job_service),
) -> AnalysisJob:
    try:
        return job_service.get(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found") from exc


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=AnalysisJob)
async def cancel_analysis_job(
    job_id: str,
    job_service: AnalysisJobService = Depends(get_job_service),
) -> AnalysisJob:
    try:
        return job_service.cancel(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found") from exc


@app.post("/analyses", response_model=SongScore, deprecated=True)
async def analyze_audio(
    audio_file: UploadFile = File(...),
    rights_confirmed: bool = Form(...),
    melody_mode: str = Form(default="vocal"),
    chord_complexity: str = Form(default="standard"),
    pipeline: AnalysisPipeline = Depends(get_pipeline),
) -> SongScore:
    """Legacy synchronous endpoint retained for API compatibility."""
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Rights must be confirmed")

    suffix = Path(audio_file.filename or "upload.wav").suffix or ".wav"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="guitarscribe_upload_") as temp_file:
            content = await audio_file.read()
            if len(content) > Settings.from_env().max_upload_bytes:
                raise HTTPException(status_code=413, detail="Audio upload exceeds the configured size limit")
            temp_file.write(content)
            temp_path = Path(temp_file.name)

        return await pipeline.run(
            SourceRequest(
                source_type=SourceType.LOCAL,
                path=temp_path,
                rights_confirmed=rights_confirmed,
            ),
            {
                "melody_mode": melody_mode,
                "chord_complexity": chord_complexity,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


@app.post("/revisions", response_model=SaveRevisionResponse)
async def save_revision(
    request: SaveRevisionRequest,
    revision_store: RevisionStore = Depends(get_revision_store),
) -> SaveRevisionResponse:
    revision_id = revision_store.save(request.score, request.revision_id)
    return SaveRevisionResponse(revision_id=revision_id)


@app.get("/revisions/{revision_id}", response_model=SongScore)
async def load_revision(
    revision_id: str,
    revision_store: RevisionStore = Depends(get_revision_store),
) -> SongScore:
    try:
        return revision_store.load(revision_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@app.post("/scores/chordpro", response_class=PlainTextResponse)
async def export_chordpro(score: SongScore) -> str:
    """Export an editable score as a chord-only ChordPro document."""
    return ChordProExporter().export(score)

@app.post("/scores/midi")
async def export_midi_score(score: SongScore) -> Response:
    return Response(content=export_midi(score), media_type="audio/midi", headers={"Content-Disposition": "attachment; filename=\"guitarscribe-melody.mid\""})

@app.post("/scores/musicxml", response_class=PlainTextResponse)
async def export_musicxml_score(score: SongScore) -> str:
    return export_musicxml(score)

class LyricsImportRequest(BaseModel):
    score: SongScore
    content: str = Field(min_length=1)
    language: str = "und"

@app.post("/scores/lyrics/import-text", response_model=SongScore)
async def import_lyrics_text(request: LyricsImportRequest) -> SongScore:
    return request.score.model_copy(update={"lyrics": import_text(request.content, request.language)})

@app.post("/scores/lyrics/import-lrc", response_model=SongScore)
async def import_lyrics_lrc(request: LyricsImportRequest) -> SongScore:
    return request.score.model_copy(update={"lyrics": import_lrc(request.content, request.language)})

@app.post("/scores/lrc", response_class=PlainTextResponse)
async def export_lrc_score(score: SongScore) -> str:
    if score.lyrics is None:
        raise HTTPException(status_code=400, detail="Score has no lyrics")
    return export_lrc(score.lyrics)

class LyricTimingRequest(BaseModel):
    score: SongScore
    line_id: str
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)

@app.post("/scores/lyrics/timing", response_model=SongScore)
async def update_lyric_timing(request: LyricTimingRequest) -> SongScore:
    if request.score.lyrics is None:
        raise HTTPException(status_code=400, detail="Score has no lyrics")
    if request.start is not None and request.end is not None and request.end < request.start:
        raise HTTPException(status_code=422, detail="Lyric end must not precede start")
    updated = []
    found = False
    for line in request.score.lyrics.lines:
        if line.id == request.line_id:
            found = True
            updated.append(line.model_copy(update={"start": request.start if request.start is not None else line.start, "end": request.end if request.end is not None else line.end, "edited": True}))
        else:
            updated.append(line)
    if not found:
        raise HTTPException(status_code=404, detail="Lyric line not found")
    lyrics = request.score.lyrics.model_copy(update={"lines": updated, "revision": request.score.lyrics.revision + 1})
    return request.score.model_copy(update={"lyrics": lyrics})

@app.get("/chord-voicings", response_model=list[ChordVoicing])
async def get_chord_voicings(symbol: str, capo: int = 0, max_fret: int = 15) -> list[ChordVoicing]:
    return ChordVoicingProvider().get(symbol, capo=capo, max_fret=max_fret)

class CapoRecommendationRequest(BaseModel):
    score: SongScore
    max_capo: int = Field(default=8, ge=0, le=12)

@app.post("/scores/capo-recommendations", response_model=list[CapoRecommendation])
async def capo_recommendations(request: CapoRecommendationRequest) -> list[CapoRecommendation]:
    return CapoAdvisor().recommend(request.score, request.max_capo)

@app.post("/scores/optimize-voicings", response_model=SongScore)
async def optimize_voicings(score: SongScore) -> SongScore:
    return SongVoicingOptimizer().optimize(score)
