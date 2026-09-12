import tempfile
from uuid import uuid4
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from .core.config import Settings
from .core.pipeline import AnalysisPipeline, create_pipeline
from .models.audio import SourceRequest, SourceType
from .models.analysis import AccidentalPreference, MelodyAnalysis, MelodyMode, RhythmSuggestion
from .models.jobs import AnalysisJob, JobStatus
from .models.analysis import ChordVoicing
from .services.voicings import ChordVoicingProvider
from .services.capo import CapoAdvisor, CapoRecommendation
from .services.voicing_optimizer import SongVoicingOptimizer
from .services.lyrics import import_lrc, import_text
from .models.score import SongScore
from .models.lyrics import LyricLine, LyricsTrack
from .services.jobs import AnalysisJobService, JobQueueFullError, JobStore, safe_audio_suffix
from .exporters.chordpro import ChordProExporter
from .exporters.lrc import export_lrc
from .exporters.midi import PlaybackManifest, compile_playback_manifest, export_midi
from .exporters.musicxml import export_musicxml
from .services.revisions import RevisionStore
from .services.transposition import TranspositionService
from .sources.youtube import YouTubeAudioDownloader, validate_youtube_url
from .services.rate_limit import SubmissionRateLimiter
from .postprocess.rhythm import RhythmSuggester
from .fretboard.mapper import SimpleFretboardMapper
from .postprocess.melody import MelodyPostProcessor


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


class LyricsReplaceRequest(BaseModel):
    lyrics: LyricsTrack


class LyricLinePatchRequest(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)


class LyricLineSplitRequest(BaseModel):
    character_index: int = Field(ge=1, description="Zero-based boundary between the retained and new lyric text.")


class LyricsRevisionResponse(BaseModel):
    revision_id: str
    score: SongScore


class YouTubeJobRequest(BaseModel):
    url: str = Field(description="A single youtube.com or youtu.be video URL. Playlists are not accepted.")
    rights_confirmed: bool = Field(description="Must be true: the caller confirms they have rights to analyze this audio.")
    melody_mode: str = Field(default="vocal", description="Melody extraction mode: vocal, guitar, or mix.")
    chord_complexity: str = Field(default="standard", description="Chord vocabulary: simple, standard, or full.")
    separate_vocals: bool = Field(default=False, description="Request optional vocal separation when the server enables it.")


OPENAPI_TAGS = [
    {"name": "System", "description": "Service health and compatibility endpoints."},
    {"name": "Analysis jobs", "description": "Asynchronous local-upload and optional YouTube analysis jobs. Poll a job until it completes or fails."},
    {"name": "Scores", "description": "Score transformations, playback compilation, and export formats."},
    {"name": "Lyrics", "description": "User-provided lyrics import, manual timing, and exports. The service never fetches third-party lyrics."},
    {"name": "Revisions", "description": "Saved editable score revisions."},
    {"name": "Guitar", "description": "Chord voicing lookup, capo advice, and voicing optimization."},
]


app = FastAPI(
    title="GuitarScribe API",
    version="0.2.0",
    description=(
        "Audio analysis, editable scores, and local background analysis jobs. "
        "Submit only audio and lyrics you are permitted to use. For long-running analysis, "
        "create a job and poll its lifecycle endpoint rather than using the legacy synchronous route."
    ),
    openapi_tags=OPENAPI_TAGS,
)
transposition_service = TranspositionService()
_job_service: AnalysisJobService | None = None
_submission_limiter: SubmissionRateLimiter | None = None

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


def get_submission_limiter() -> SubmissionRateLimiter:
    global _submission_limiter
    if _submission_limiter is None:
        settings = Settings.from_env()
        _submission_limiter = SubmissionRateLimiter(settings.submission_rate_limit, settings.submission_rate_window_seconds)
    return _submission_limiter


async def enforce_submission_rate_limit(request: Request, limiter: SubmissionRateLimiter = Depends(get_submission_limiter)) -> None:
    client_key = request.client.host if request.client else "unknown"
    allowed, retry_after = limiter.allow(client_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many analysis submissions; try again later.",
            headers={"Retry-After": str(retry_after)},
        )


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
        max_queued_jobs=settings.max_queued_jobs,
        job_ttl_seconds=settings.job_ttl_seconds,
        youtube_downloader=YouTubeAudioDownloader(settings.youtube_dl_binary, settings.youtube_download_timeout_seconds, settings.max_upload_bytes) if settings.youtube_enabled else None,
        )
    return _job_service


@app.get("/health", response_model=HealthResponse, tags=["System"], summary="Check service health")
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/scores/transpose", response_model=SongScore, tags=["Scores"], summary="Transpose an editable score")
async def transpose_score(request: TransposeScoreRequest) -> SongScore:
    return transposition_service.transpose_score(
        score=request.score,
        semitones=request.semitones,
        accidental_preference=request.accidental_preference,
        capo=request.capo,
    )


@app.post("/scores/remap-tab", response_model=SongScore, tags=["Scores"], summary="Remap melody Tab using saved guitar preferences")
async def remap_tab(score: SongScore) -> SongScore:
    result = score.model_copy(deep=True)
    result.melody = SimpleFretboardMapper().map_notes(
        MelodyAnalysis(notes=result.melody),
        capo=result.analysis.capo,
        max_fret=result.guitar.max_fret,
        preference=result.guitar.tab_preference,
    ).notes
    return result


class SimplifyMelodyRequest(BaseModel):
    score: SongScore
    mode: MelodyMode = MelodyMode.VOCAL
    min_confidence: float = Field(default=0.55, ge=0, le=1)
    min_duration: float = Field(default=0.16, ge=0.04, le=2)


@app.post("/scores/melody/simplify", response_model=SongScore, tags=["Scores"], summary="Create a cleaner editable melody draft without DSP")
async def simplify_melody(request: SimplifyMelodyRequest) -> SongScore:
    """Apply stricter note cleanup to an existing analysis result.

    This is intentionally a reversible score edit, not a second transcription.
    It removes low-confidence/very short candidates, restores a monophonic
    contour, and rebuilds the displayed Tab positions.
    """
    result = request.score.model_copy(deep=True)
    processor = MelodyPostProcessor()
    notes = processor.remove_low_confidence(result.melody, request.min_confidence)
    notes = processor.remove_short_notes(notes, request.min_duration)
    notes = processor.quantize_to_beats(notes, result.beats)
    notes = processor.select_monophonic_line(notes, request.mode)
    notes = processor.remove_isolated_pitch_leaps(notes)
    notes = processor.remove_register_outliers(notes)
    notes = processor.merge_repeated(notes)
    result.melody = SimpleFretboardMapper().map_notes(
        MelodyAnalysis(notes=notes),
        capo=result.analysis.capo,
        max_fret=result.guitar.max_fret,
        preference=result.guitar.tab_preference,
    ).notes
    warning = "Melody was simplified from the existing estimate; compare it with the source audio and use Undo to restore all candidates."
    if warning not in result.analysis.warnings:
        result.analysis.warnings.append(warning)
    return result


@app.get("/rhythm-patterns", response_model=list[RhythmSuggestion], tags=["Scores"], summary="List local playable rhythm templates")
async def list_rhythm_patterns(time_signature: str = "4/4") -> list[RhythmSuggestion]:
    """Expose data-only local templates for manual score accompaniment edits."""
    return RhythmSuggester(Settings.from_env().rhythm_patterns_dir).available_patterns(time_signature)


@app.post(
    "/api/v1/jobs",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analysis jobs"],
    summary="Queue an uploaded audio file for analysis",
    description="Returns immediately. Poll `GET /api/v1/jobs/{job_id}` until the job is completed, failed, or cancelled.",
)
async def create_analysis_job(
    audio_file: UploadFile = File(...),
    rights_confirmed: bool = Form(...),
    melody_mode: str = Form(default="vocal"),
    chord_complexity: str = Form(default="standard"),
    separate_vocals: bool = Form(default=False),
    _rate_limit: None = Depends(enforce_submission_rate_limit),
    job_service: AnalysisJobService = Depends(get_job_service),
) -> AnalysisJob:
    """Queue a local upload for analysis and return immediately."""
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Rights must be confirmed")
    content = await audio_file.read()
    if len(content) > Settings.from_env().max_upload_bytes:
        raise HTTPException(status_code=413, detail="Audio upload exceeds the configured size limit")
    try:
        return await job_service.submit(
            filename=audio_file.filename or "upload.wav",
            content=content,
            melody_mode=melody_mode,
            separate_vocals=separate_vocals,
            chord_complexity=chord_complexity,
        )
    except JobQueueFullError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "30"}) from exc


@app.post(
    "/api/v1/youtube-jobs",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Analysis jobs"],
    summary="Queue a permitted single-video YouTube analysis",
    description="Available only when the server enables the resolver. Cookies, credentials, playlists, and arbitrary downloader arguments are never accepted.",
)
async def create_youtube_analysis_job(
    request: YouTubeJobRequest,
    _rate_limit: None = Depends(enforce_submission_rate_limit),
    job_service: AnalysisJobService = Depends(get_job_service),
) -> AnalysisJob:
    if not request.rights_confirmed:
        raise HTTPException(status_code=400, detail="Rights must be confirmed")
    try:
        return await job_service.submit_youtube(validate_youtube_url(request.url), request.melody_mode, request.chord_complexity, request.separate_vocals)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/jobs/{job_id}", response_model=AnalysisJob, tags=["Analysis jobs"], summary="Read job status and result")
async def get_analysis_job(
    job_id: str,
    job_service: AnalysisJobService = Depends(get_job_service),
) -> AnalysisJob:
    try:
        return job_service.get(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found") from exc


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=AnalysisJob, tags=["Analysis jobs"], summary="Cancel a queued or running analysis job")
async def cancel_analysis_job(
    job_id: str,
    job_service: AnalysisJobService = Depends(get_job_service),
) -> AnalysisJob:
    try:
        return job_service.cancel(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found") from exc


@app.get("/api/v1/jobs/{job_id}/audio", tags=["Analysis jobs"], summary="Download normalized source audio for a completed job")
async def get_job_audio(job_id: str, job_service: AnalysisJobService = Depends(get_job_service)) -> FileResponse:
    try:
        job = job_service.get(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found") from exc
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Audio is available after analysis completes")
    candidates = list(job_service.store.job_dir(job_id).glob("input.wav"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Job audio is unavailable")
    return FileResponse(candidates[0], media_type="audio/wav", filename="guitarscribe-source.wav")


@app.post("/analyses", response_model=SongScore, deprecated=True, tags=["Analysis jobs"], summary="Analyze an upload synchronously (legacy)")
async def analyze_audio(
    audio_file: UploadFile = File(...),
    rights_confirmed: bool = Form(...),
    melody_mode: str = Form(default="vocal"),
    chord_complexity: str = Form(default="standard"),
    separate_vocals: bool = Form(default=False),
    pipeline: AnalysisPipeline = Depends(get_pipeline),
) -> SongScore:
    """Legacy synchronous endpoint retained for API compatibility."""
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Rights must be confirmed")

    suffix = safe_audio_suffix(audio_file.filename)
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
                "separate_vocals": separate_vocals,
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


@app.post("/revisions", response_model=SaveRevisionResponse, tags=["Revisions"], summary="Save an editable score revision")
async def save_revision(
    request: SaveRevisionRequest,
    revision_store: RevisionStore = Depends(get_revision_store),
) -> SaveRevisionResponse:
    revision_id = revision_store.save(request.score, request.revision_id)
    return SaveRevisionResponse(revision_id=revision_id)


@app.get("/revisions/{revision_id}", response_model=SongScore, tags=["Revisions"], summary="Load an editable score revision")
async def load_revision(
    revision_id: str,
    revision_store: RevisionStore = Depends(get_revision_store),
) -> SongScore:
    try:
        return revision_store.load(revision_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/revisions/{revision_id}/lyrics", response_model=LyricsTrack, tags=["Lyrics"], summary="Read lyrics from a saved score revision")
async def load_revision_lyrics(revision_id: str, revision_store: RevisionStore = Depends(get_revision_store)) -> LyricsTrack:
    try:
        lyrics = revision_store.load(revision_id).lyrics
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if lyrics is None:
        raise HTTPException(status_code=404, detail="Revision has no lyrics")
    return lyrics


def _fork_lyrics_revision(revision_id: str, lyrics: LyricsTrack, revision_store: RevisionStore) -> LyricsRevisionResponse:
    try:
        score = revision_store.load(revision_id)
        next_score = score.model_copy(update={"lyrics": lyrics})
        next_revision_id = revision_store.fork(revision_id, next_score)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return LyricsRevisionResponse(revision_id=next_revision_id, score=next_score)


@app.put("/revisions/{revision_id}/lyrics", response_model=LyricsRevisionResponse, tags=["Lyrics"], summary="Replace lyrics and fork a score revision")
async def replace_revision_lyrics(
    revision_id: str,
    request: LyricsReplaceRequest,
    revision_store: RevisionStore = Depends(get_revision_store),
) -> LyricsRevisionResponse:
    return _fork_lyrics_revision(
        revision_id,
        request.lyrics.model_copy(update={"revision": request.lyrics.revision + 1}),
        revision_store,
    )


@app.patch("/revisions/{revision_id}/lyrics/lines/{line_id}", response_model=LyricsRevisionResponse, tags=["Lyrics"], summary="Patch one lyric line and fork a score revision")
async def patch_revision_lyric_line(
    revision_id: str,
    line_id: str,
    request: LyricLinePatchRequest,
    revision_store: RevisionStore = Depends(get_revision_store),
) -> LyricsRevisionResponse:
    try:
        lyrics = revision_store.load(revision_id).lyrics
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if lyrics is None:
        raise HTTPException(status_code=404, detail="Revision has no lyrics")
    patch = request.model_dump(exclude_unset=True, exclude_none=True)
    if not patch:
        raise HTTPException(status_code=422, detail="Provide at least one lyric line field to update")
    updated_lines: list[LyricLine] = []
    found = False
    for line in lyrics.lines:
        if line.id != line_id:
            updated_lines.append(line)
            continue
        found = True
        next_line = line.model_copy(update={**patch, "edited": True, "origin": "user"})
        if next_line.start is not None and next_line.end is not None and next_line.end < next_line.start:
            raise HTTPException(status_code=422, detail="Lyric end must not precede start")
        updated_lines.append(next_line)
    if not found:
        raise HTTPException(status_code=404, detail="Lyric line not found")
    return _fork_lyrics_revision(
        revision_id,
        lyrics.model_copy(update={"lines": updated_lines, "revision": lyrics.revision + 1}),
        revision_store,
    )


def _renumber_lyric_lines(lines: list[LyricLine]) -> list[LyricLine]:
    return [line.model_copy(update={"order": index}) for index, line in enumerate(lines)]


@app.post("/revisions/{revision_id}/lyrics/lines/{line_id}/split", response_model=LyricsRevisionResponse, tags=["Lyrics"], summary="Split one lyric line and fork a score revision")
async def split_revision_lyric_line(
    revision_id: str,
    line_id: str,
    request: LyricLineSplitRequest,
    revision_store: RevisionStore = Depends(get_revision_store),
) -> LyricsRevisionResponse:
    try:
        lyrics = revision_store.load(revision_id).lyrics
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if lyrics is None:
        raise HTTPException(status_code=404, detail="Revision has no lyrics")
    lines = sorted(lyrics.lines, key=lambda line: line.order)
    index = next((line_index for line_index, line in enumerate(lines) if line.id == line_id), -1)
    if index < 0:
        raise HTTPException(status_code=404, detail="Lyric line not found")
    line = lines[index]
    if request.character_index >= len(line.text):
        raise HTTPException(status_code=422, detail="Split must fall inside lyric text")
    before = line.text[:request.character_index].rstrip()
    after = line.text[request.character_index:].lstrip()
    if not before or not after:
        raise HTTPException(status_code=422, detail="Split must leave text on both lyric lines")
    split_time = None
    if line.start is not None and line.end is not None:
        split_time = line.start + (line.end - line.start) * (request.character_index / len(line.text))
    first_words = [word for word in line.words if split_time is None or (word.start + word.end) / 2 <= split_time]
    second_words = [word for word in line.words if split_time is None or (word.start + word.end) / 2 > split_time]
    first = line.model_copy(update={"text": before, "end": split_time, "words": first_words, "edited": True, "origin": "user"})
    second = LyricLine(
        id=f"{line.id}-split-{uuid4().hex[:8]}", order=line.order + 1,
        text=after, start=split_time, end=line.end, words=second_words,
        confidence=line.confidence, edited=True, origin="user",
    )
    return _fork_lyrics_revision(
        revision_id,
        lyrics.model_copy(update={"lines": _renumber_lyric_lines([*lines[:index], first, second, *lines[index + 1:]]), "revision": lyrics.revision + 1}),
        revision_store,
    )


@app.post("/revisions/{revision_id}/lyrics/lines/{line_id}/merge-next", response_model=LyricsRevisionResponse, tags=["Lyrics"], summary="Merge a lyric line with its next line and fork a score revision")
async def merge_revision_lyric_line_with_next(
    revision_id: str,
    line_id: str,
    revision_store: RevisionStore = Depends(get_revision_store),
) -> LyricsRevisionResponse:
    try:
        lyrics = revision_store.load(revision_id).lyrics
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if lyrics is None:
        raise HTTPException(status_code=404, detail="Revision has no lyrics")
    lines = sorted(lyrics.lines, key=lambda line: line.order)
    index = next((line_index for line_index, line in enumerate(lines) if line.id == line_id), -1)
    if index < 0:
        raise HTTPException(status_code=404, detail="Lyric line not found")
    if index + 1 >= len(lines):
        raise HTTPException(status_code=422, detail="Cannot merge the final lyric line")
    line, next_line = lines[index], lines[index + 1]
    merged = line.model_copy(update={
        "text": f"{line.text.rstrip()} {next_line.text.lstrip()}".strip(),
        "end": next_line.end if next_line.end is not None else line.end,
        "words": [*line.words, *next_line.words],
        "edited": True,
        "origin": "user",
    })
    return _fork_lyrics_revision(
        revision_id,
        lyrics.model_copy(update={"lines": _renumber_lyric_lines([*lines[:index], merged, *lines[index + 2:]]), "revision": lyrics.revision + 1}),
        revision_store,
    )

@app.post("/scores/chordpro", response_class=PlainTextResponse)
async def export_chordpro(score: SongScore) -> str:
    """Export an editable score as a chord-only ChordPro document."""
    return ChordProExporter().export(score)

@app.post("/scores/midi")
async def export_midi_score(score: SongScore) -> Response:
    return Response(content=export_midi(score), media_type="audio/midi", headers={"Content-Disposition": "attachment; filename=\"guitarscribe-melody.mid\""})

@app.post("/scores/playback/manifest", response_model=PlaybackManifest)
async def compile_score_playback(score: SongScore) -> PlaybackManifest:
    return compile_playback_manifest(score)

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

@app.post("/scores/lyrics/distribute-timing", response_model=SongScore)
async def distribute_lyric_timing(score: SongScore) -> SongScore:
    if score.lyrics is None or not score.lyrics.lines:
        raise HTTPException(status_code=400, detail="Score has no lyric lines")
    duration = score.song.duration_seconds / len(score.lyrics.lines)
    lines = [line.model_copy(update={"start": index * duration, "end": (index + 1) * duration, "edited": True}) for index, line in enumerate(score.lyrics.lines)]
    return score.model_copy(update={"lyrics": score.lyrics.model_copy(update={"lines": lines, "revision": score.lyrics.revision + 1})})


@app.post("/scores/lyrics/fit-timing-to-bars", response_model=SongScore)
async def fit_lyric_timing_to_bars(score: SongScore) -> SongScore:
    """Create editable line timing suggestions from detected musical boundaries.

    This is structural assistance, not lyric recognition or forced alignment.
    It uses measure starts where there are enough of them, then beat starts,
    and safely falls back to even timing for very short analyses.
    """
    if score.lyrics is None or not score.lyrics.lines:
        raise HTTPException(status_code=400, detail="Score has no lyric lines")
    line_count = len(score.lyrics.lines)
    measure_starts = sorted({beat.time for beat in score.beats if beat.beat == 1})
    beat_starts = sorted({beat.time for beat in score.beats})
    anchors = measure_starts if len(measure_starts) >= line_count else beat_starts if len(beat_starts) >= line_count else []
    if not anchors:
        return await distribute_lyric_timing(score)

    def boundary(index: int) -> float:
        anchor_index = (index * len(anchors)) // line_count
        return anchors[anchor_index] if anchor_index < len(anchors) else score.song.duration_seconds

    lines = [
        line.model_copy(update={
            "start": boundary(index),
            "end": boundary(index + 1) if index + 1 < line_count else score.song.duration_seconds,
            "confidence": min(line.confidence, 0.55),
            "origin": "alignment",
            "edited": True,
        })
        for index, line in enumerate(score.lyrics.lines)
    ]
    lyrics = score.lyrics.model_copy(update={"lines": lines, "revision": score.lyrics.revision + 1})
    return score.model_copy(update={"lyrics": lyrics})

class LyricTimingRequest(BaseModel):
    score: SongScore
    line_id: str
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)

@app.post("/scores/lyrics/timing", response_model=SongScore)
async def update_lyric_timing(request: LyricTimingRequest) -> SongScore:
    if request.score.lyrics is None:
        raise HTTPException(status_code=400, detail="Score has no lyrics")
    updated = []
    found = False
    for line in request.score.lyrics.lines:
        if line.id == request.line_id:
            found = True
            start = request.start if request.start is not None else line.start
            end = request.end if request.end is not None else line.end
            if start is not None and end is not None and end < start:
                raise HTTPException(status_code=422, detail="Lyric end must not precede start")
            updated.append(line.model_copy(update={"start": start, "end": end, "edited": True}))
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
