import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .core.config import Settings
from .core.pipeline import AnalysisPipeline, create_pipeline
from .models.audio import SourceRequest, SourceType
from .models.analysis import AccidentalPreference
from .models.score import SongScore
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


app = FastAPI(title="GuitarScribe API", version="0.1.0")
transposition_service = TranspositionService()

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


@app.post("/analyses", response_model=SongScore)
async def analyze_audio(
    audio_file: UploadFile = File(...),
    rights_confirmed: bool = Form(...),
    melody_mode: str = Form(default="vocal"),
    chord_complexity: str = Form(default="standard"),
    pipeline: AnalysisPipeline = Depends(get_pipeline),
) -> SongScore:
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Rights must be confirmed")

    suffix = Path(audio_file.filename or "upload.wav").suffix or ".wav"
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix="guitarscribe_upload_") as temp_file:
            temp_file.write(await audio_file.read())
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
