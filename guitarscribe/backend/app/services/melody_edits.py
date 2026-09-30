"""Explicit, non-DSP edits to a working score; source artifacts stay untouched."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field

from ..models.analysis import MelodyAnalysis, MelodyNote
from ..models.score import SongScore, MelodyEditRecord
from ..fretboard.mapper import SimpleFretboardMapper
from .transposition import TranspositionService


class MelodyEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    score: SongScore
    operation: Literal["add", "update", "delete", "split", "merge_next"]
    note_id: str | None = None
    midi: int | None = Field(default=None, ge=0, le=127, strict=True)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    split_time: float | None = Field(default=None, ge=0)
    source_job_id: str | None = Field(default=None, max_length=128)


class MelodyEditResponse(BaseModel):
    score: SongScore
    selected_note_id: str | None


def edit_melody(request: MelodyEditRequest) -> MelodyEditResponse:
    result = request.score.model_copy(deep=True)
    if not isfinite(result.song.duration_seconds) or result.song.duration_seconds <= 0:
        raise ValueError("Song duration must be finite and positive")
    if len({n.id for n in result.melody}) != len(result.melody):
        raise ValueError("Duplicate note IDs; cannot safely select an event")
    notes = sorted(result.melody, key=lambda n: (n.start, n.end, n.id))
    selected = next((n for n in notes if n.id == request.note_id), None)
    if request.operation != "add" and selected is None:
        raise ValueError("Selected note no longer exists")
    before = [selected.model_copy(deep=True)] if selected and request.operation != "add" else []
    changed: list[MelodyNote] = []
    removed = {selected.id} if selected and request.operation != "add" else set()
    naming = TranspositionService()
    if request.operation in {"add", "update"}:
        if request.start is None or request.end is None or request.midi is None:
            raise ValueError("Pitch, start and end are required")
        note = selected.model_copy(deep=True) if request.operation == "update" else MelodyNote(
            id=f"user-{uuid4().hex}", start=request.start, end=request.end,
            midi=request.midi, note="", confidence=0,
        )
        if request.operation == "add" or note.midi != request.midi:
            source_midi = request.midi - result.key_context.transpose_semitones
            if not 0 <= source_midi <= 127:
                raise ValueError("Pitch is outside MIDI range in the source key")
            note.source_midi = source_midi
            note.source_note = naming.note_name_from_midi(source_midi, result.key_context.source.key,
                result.key_context.accidental_preference, result.key_context.source.mode)
        note.start, note.end, note.midi = request.start, request.end, request.midi
        note.note = naming.note_name_from_midi(note.midi, result.analysis.key,
            result.key_context.accidental_preference, result.analysis.mode)
        changed = [note]
    elif request.operation == "split":
        if request.split_time is None or not selected.start < request.split_time < selected.end:
            raise ValueError("Split position must be inside the selected note")
        changed = [selected.model_copy(update={"end": request.split_time}),
                   selected.model_copy(update={"id": f"user-{uuid4().hex}", "start": request.split_time})]
    elif request.operation == "merge_next":
        index = notes.index(selected)
        following = notes[index + 1] if index + 1 < len(notes) else None
        if following is None or following.midi != selected.midi or abs(following.start - selected.end) > 1e-6:
            raise ValueError("Merge requires a touching next note of the same pitch; rests are not filled")
        before.append(following.model_copy(deep=True))
        removed.add(following.id)
        changed = [selected.model_copy(update={"end": following.end,
                                                "confidence": min(selected.confidence, following.confidence)})]
    remaining = [n for n in notes if n.id not in removed]
    for note in changed:
        if not 0 <= note.start < note.end <= result.song.duration_seconds or note.end - note.start < 0.01 - 1e-9:
            raise ValueError("Notes must be at least 0.01s long and stay within the song")
        if any(note.start < other.end - 1e-8 and other.start < note.end - 1e-8 for other in remaining):
            raise ValueError("Edited note overlaps another note; adjust the timing or delete the conflicting note first")
        note.origin, note.edited = "user", True
        note.string, note.fret = None, None
    result.melody = sorted(remaining + changed, key=lambda n: (n.start, n.end, n.id))
    mapper = SimpleFretboardMapper()
    mapper.string_tuning = result.guitar.tuning
    if len(mapper.string_tuning) != 6:
        raise ValueError("Tab mapping currently requires a six-string tuning")
    mapped = mapper.map_notes(MelodyAnalysis(notes=result.melody), capo=result.analysis.capo,
                              max_fret=result.guitar.max_fret, preference=result.guitar.tab_preference).notes
    # Only affected notes get new fingering; other score events remain untouched.
    changed_ids = {n.id for n in changed}
    mapped_by_id = {n.id: n for n in mapped}
    result.melody = [mapped_by_id[n.id] if n.id in changed_ids else n for n in result.melody]
    result.melody_edits.append(MelodyEditRecord(
        id=uuid4().hex, operation=request.operation, created_at=datetime.now(timezone.utc).isoformat(),
        source_job_id=request.source_job_id, transpose_semitones=result.key_context.transpose_semitones,
        before=before, after=[n.model_copy(deep=True) for n in result.melody if n.id in changed_ids],
    ))
    return MelodyEditResponse(score=result, selected_note_id=changed[0].id if changed else None)
