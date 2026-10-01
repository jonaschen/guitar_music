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
    operation: Literal["add", "update", "delete", "split", "merge_next", "shift_phrase"]
    note_id: str | None = None
    midi: int | None = Field(default=None, ge=0, le=127, strict=True)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, ge=0)
    split_time: float | None = Field(default=None, ge=0)
    source_job_id: str | None = Field(default=None, max_length=128)
    string: int | None = Field(default=None, ge=1, le=6, strict=True)
    fret: int | None = Field(default=None, ge=0, strict=True)
    range_start: float | None = Field(default=None, ge=0)
    range_end: float | None = Field(default=None, ge=0)
    target_start: float | None = Field(default=None, ge=0)


class MelodyEditResponse(BaseModel):
    score: SongScore
    selected_note_id: str | None


def shift_phrase(request: MelodyEditRequest, result: SongScore) -> MelodyEditResponse:
    start, end, target = request.range_start, request.range_end, request.target_start
    if start is None or end is None or target is None or not 0 <= start < end <= result.song.duration_seconds:
        raise ValueError("請選擇有效的段落範圍。")
    if any(n.start < start < n.end for n in result.melody):
        raise ValueError("段落開頭有跨小節延續音，並非空白；請把選取範圍往前擴大。")
    before = sorted((n.model_copy(deep=True) for n in result.melody if start <= n.start < end), key=lambda n: (n.start, n.end))
    if not before:
        raise ValueError("所選段落沒有旋律音符。")
    delta = before[0].start - target
    if target < start or delta <= 1e-8:
        raise ValueError("目標必須位於所選段落內、第一音之前的空白。")
    starts = {}
    for beat in result.beats:
        starts[beat.measure] = min(starts.get(beat.measure, beat.time), beat.time)
    boundaries = sorted(set([0.0, *starts.values(), result.song.duration_seconds]))
    if starts:
        index = max(i for i, time in enumerate(boundaries[:-1]) if time <= before[0].start)
        bar_seconds = boundaries[index + 1] - boundaries[index]
    else:
        numerator, denominator = map(int, result.analysis.time_signature.split("/"))
        bar_seconds = 60 / max(1, result.analysis.bpm) * numerator * 4 / denominator
    if delta >= bar_seconds - 1e-8:
        raise ValueError("前移量必須小於第一音所在的一個小節；請選更接近第一音的起始小節或目標位置。")
    ids = {n.id for n in before}
    after = [n.model_copy(update={"start": n.start - delta, "end": n.end - delta, "origin": "user", "edited": True}) for n in before]
    if any(not isfinite(n.start) or not isfinite(n.end) or not 0 <= n.start < n.end <= result.song.duration_seconds for n in after):
        raise ValueError("音符時間無效或超出歌曲範圍，未套用。")
    remaining = [n for n in result.melody if n.id not in ids]
    if any(n.start < other.end - 1e-8 and other.start < n.end - 1e-8 for n in after for other in remaining):
        raise ValueError("前移後會碰到段落外音符，未套用；請調整範圍或減少前移量。")
    result.melody = sorted(remaining + after, key=lambda n: (n.start, n.end, n.id))
    result.melody_edits.append(MelodyEditRecord(
        id=uuid4().hex, operation="shift_phrase", created_at=datetime.now(timezone.utc).isoformat(),
        source_job_id=request.source_job_id, transpose_semitones=result.key_context.transpose_semitones,
        before=before, after=[n.model_copy(deep=True) for n in after],
    ))
    return MelodyEditResponse(score=result, selected_note_id=after[0].id)


def edit_melody(request: MelodyEditRequest) -> MelodyEditResponse:
    result = request.score.model_copy(deep=True)
    if not isfinite(result.song.duration_seconds) or result.song.duration_seconds <= 0:
        raise ValueError("Song duration must be finite and positive")
    if len({n.id for n in result.melody}) != len(result.melody):
        raise ValueError("Duplicate note IDs; cannot safely select an event")
    if request.operation == "shift_phrase":
        return shift_phrase(request, result)
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
    # Time-only edits and splits must not relocate a fingering the user chose.
    if selected and selected.string is not None and selected.fret is not None:
        if (1 <= selected.string <= 6 and 0 <= selected.fret <= result.guitar.max_fret
                and result.guitar.tuning[6 - selected.string] + result.analysis.capo + selected.fret == selected.midi):
            for note in result.melody:
                if note.id in changed_ids and note.midi == selected.midi:
                    note.string, note.fret = selected.string, selected.fret
    if request.string is not None or request.fret is not None:
        if request.operation not in {"add", "update"} or request.string is None or request.fret is None:
            raise ValueError("Supply both string and fret for an add or update")
        if request.fret > result.guitar.max_fret:
            raise ValueError("Fret exceeds the configured maximum")
        sounding = result.guitar.tuning[6 - request.string] + result.analysis.capo + request.fret
        if sounding != request.midi:
            raise ValueError("String and fret do not match the sounding pitch with this tuning and capo")
        for note in result.melody:
            if note.id in changed_ids:
                note.string, note.fret = request.string, request.fret
    result.melody_edits.append(MelodyEditRecord(
        id=uuid4().hex, operation=request.operation, created_at=datetime.now(timezone.utc).isoformat(),
        source_job_id=request.source_job_id, transpose_semitones=result.key_context.transpose_semitones,
        before=before, after=[n.model_copy(deep=True) for n in result.melody if n.id in changed_ids],
    ))
    return MelodyEditResponse(score=result, selected_note_id=changed[0].id if changed else None)
