import logging
import numpy as np
import librosa
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, ChordAnalysis, ChordEvent

logger = logging.getLogger(__name__)

ROOTS = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
ROOT_TO_PITCH = {root: index for index, root in enumerate(ROOTS)}

def get_chord_templates():
    templates = []
    labels = []
    
    maj_template = np.array([1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0])
    min_template = np.array([1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0])
    
    for i in range(12):
        templates.append(np.roll(maj_template, i))
        labels.append(ROOTS[i])
        
    for i in range(12):
        templates.append(np.roll(min_template, i))
        labels.append(ROOTS[i] + 'm')
        
    templates.append(np.zeros(12))
    labels.append("N")
    
    return np.vstack(templates), labels


def _group_segments(segments: list[tuple[float, float, str, float]]) -> list[ChordEvent]:
    events: list[ChordEvent] = []
    for start, end, label, confidence in segments:
        if label == "N" or end <= start:
            continue
        if events and events[-1].symbol == label and abs(events[-1].end - start) < 0.02:
            previous_duration = events[-1].end - events[-1].start
            segment_duration = end - start
            events[-1].confidence = (
                events[-1].confidence * previous_duration + confidence * segment_duration
            ) / max(previous_duration + segment_duration, 1e-6)
            events[-1].end = end
        else:
            events.append(ChordEvent(
                id=f"chord-{len(events) + 1}", start=start, end=end,
                symbol=label, confidence=round(confidence, 3),
            ))
    return events


def decode_beat_synchronous_chords(
    similarities: np.ndarray,
    frame_times: np.ndarray,
    beats: BeatAnalysis,
    duration_seconds: float,
    labels: list[str],
) -> list[ChordEvent]:
    """Aggregate frame-level chord evidence into notation-friendly beat slots."""
    boundaries = [0.0]
    boundaries.extend(beat.time for beat in beats.beats if 0.02 < beat.time < duration_seconds - 0.02)
    boundaries.append(duration_seconds)
    boundaries = sorted(set(boundaries))
    segments: list[tuple[float, float, str, float]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        indexes = np.flatnonzero((frame_times >= start) & (frame_times < end))
        if not len(indexes):
            continue
        scores = np.mean(similarities[:, indexes], axis=1)
        best_index = int(np.argmax(scores))
        ordered = np.sort(scores)
        best = float(ordered[-1])
        margin = best - float(ordered[-2]) if len(ordered) > 1 else best
        label = "N" if best < 0.18 else labels[best_index]
        confidence = max(0.05, min(0.95, 0.45 + margin))
        segments.append((float(start), float(end), label, confidence))
    return _group_segments(segments)


def estimate_key_from_chords(events: list[ChordEvent]) -> tuple[str, str]:
    """Choose the major/minor key with the strongest duration-weighted triad fit."""
    if not events:
        return "C", "major"
    scored: list[tuple[float, str, str]] = []
    for tonic_name, tonic in ROOT_TO_PITCH.items():
        for mode in ("major", "minor"):
            compatible = (
                {(0, False), (2, True), (4, True), (5, False), (7, False), (9, True)}
                if mode == "major"
                else {(0, True), (3, False), (5, True), (7, True), (7, False), (8, False), (10, False)}
            )
            score = 0.0
            for event in events:
                root_name = event.symbol[:-1] if event.symbol.endswith("m") else event.symbol
                root = ROOT_TO_PITCH.get(root_name)
                if root is None:
                    continue
                is_minor = event.symbol.endswith("m")
                duration = max(0.0, event.end - event.start)
                degree = (root - tonic) % 12
                if (degree, is_minor) in compatible:
                    score += duration
                if degree == 0 and is_minor == (mode == "minor"):
                    score += duration * 0.35
            scored.append((score, tonic_name, mode))
    _, key, mode = max(scored, key=lambda item: item[0])
    return key, mode


def normalize_low_confidence_qualities(
    events: list[ChordEvent], key: str, mode: str, threshold: float = 0.6
) -> list[ChordEvent]:
    """Resolve weak major/minor ambiguity using the estimated key.

    Chromagrams often alternate between parallel major and minor templates on
    noisy beats.  A lead sheet should not expose that uncertainty as changes
    such as Bb-Bbm-Bb when only Bb belongs to the inferred key.
    """
    tonic = ROOT_TO_PITCH.get(key)
    if tonic is None:
        return events
    allowed = (
        {(0, False), (2, True), (4, True), (5, False), (7, False), (9, True)}
        if mode == "major"
        else {(0, True), (3, False), (5, True), (7, True), (7, False), (8, False), (10, False)}
    )
    normalized: list[tuple[float, float, str, float]] = []
    for event in events:
        root_name = event.symbol[:-1] if event.symbol.endswith("m") else event.symbol
        root = ROOT_TO_PITCH.get(root_name)
        is_minor = event.symbol.endswith("m")
        label = event.symbol
        if root is not None and event.confidence < threshold:
            degree = (root - tonic) % 12
            if (degree, is_minor) not in allowed and (degree, not is_minor) in allowed:
                label = root_name if is_minor else f"{root_name}m"
        normalized.append((event.start, event.end, label, event.confidence))
    return _group_segments(normalized)

class ChromagramChordAnalyzer:
    async def analyze(self, audio: NormalizedAudio, beats: BeatAnalysis) -> ChordAnalysis:
        logger.info(f"Analyzing chords with chromagram for {audio.path}")
        try:
            y, sr = librosa.load(str(audio.path), sr=audio.sample_rate)
            hop_length = 2048
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
            
            templates, labels = get_chord_templates()
            
            # Cosine similarity
            chroma_norm = chroma / (np.linalg.norm(chroma, axis=0) + 1e-6)
            templates_norm = templates / (np.linalg.norm(templates, axis=1, keepdims=True) + 1e-6)
            
            similarities = np.dot(templates_norm, chroma_norm)
            best_chords = np.argmax(similarities, axis=0)
            
            times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length)
            
            if len(beats.beats) >= 2:
                events = decode_beat_synchronous_chords(similarities, times, beats, audio.duration_seconds, labels)
            else:
                segments = []
                current_label = None
                start_time = 0.0
                for i, chord_id in enumerate(best_chords):
                    label = labels[chord_id]
                    t = float(times[i])
                    if label != current_label:
                        if current_label is not None:
                            segments.append((start_time, t, current_label, 0.5))
                        current_label, start_time = label, t
                if current_label is not None:
                    segments.append((start_time, float(audio.duration_seconds), current_label, 0.5))
                events = _group_segments(segments)

            key, mode = estimate_key_from_chords(events)
            events = normalize_low_confidence_qualities(events, key, mode)
                
            return ChordAnalysis(
                chords=events,
                key=key,
                mode=mode,
                confidence=0.6,
                engine="chromagram",
                engine_version="1.0"
            )
            
        except Exception as e:
            logger.error(f"Chromagram analysis failed: {e}")
            raise RuntimeError(f"Chromagram analysis failed: {e}")
