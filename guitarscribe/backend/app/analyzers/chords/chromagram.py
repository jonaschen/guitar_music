import logging
from dataclasses import asdict, dataclass
import numpy as np
import librosa
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, ChordAnalysis, ChordEvent, ChordLabelCandidate
from ...postprocess.harmony import parse_chord, tonal_bias

logger = logging.getLogger(__name__)

ROOTS = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
ROOT_TO_PITCH = {root: index for index, root in enumerate(ROOTS)}


@dataclass(frozen=True)
class ChordDecoderConfig:
    change_threshold: float = 0.12
    no_chord_threshold: float = 0.18
    base_change_penalty: float = 0.04
    short_event_change_penalty: float = 0.05
    circle_fifths_bonus: float = 0.015
    tonal_prior_scale: float = 1.0

    def parameters(self) -> dict[str, float]:
        return {f"decoder_{key}": value for key, value in asdict(self).items()}

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


def _evidence_distance(left: np.ndarray, right: np.ndarray) -> float:
    """Compare chord evidence while ignoring changes in overall loudness."""
    left = left - np.mean(left)
    right = right - np.mean(right)
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm < 1e-8 and right_norm < 1e-8:
        return 0.0
    if left_norm < 1e-8 or right_norm < 1e-8:
        return 1.0
    similarity = float(np.dot(left, right) / (left_norm * right_norm))
    return 1.0 - max(-1.0, min(1.0, similarity))


def _detect_harmonic_regions(
    similarities: np.ndarray,
    frame_times: np.ndarray,
    boundaries: list[float],
    change_threshold: float = 0.12,
) -> list[tuple[float, float, np.ndarray]]:
    """Find harmonic changes before assigning chord labels.

    Beat positions constrain where a lead-sheet change may occur, but they do
    not force a new chord on every beat. Adjacent beat slots with nearly the
    same complete template-evidence profile are decoded as one region. This
    also suppresses tiny C/G (or major/minor) argmax flips caused by noise.
    """
    slots: list[tuple[float, float, np.ndarray, np.ndarray]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        indexes = np.flatnonzero((frame_times >= start) & (frame_times < end))
        if len(indexes):
            slots.append((float(start), float(end), indexes, np.mean(similarities[:, indexes], axis=1)))
    if not slots:
        return []

    regions: list[tuple[float, float, np.ndarray]] = []
    region_start = slots[0][0]
    region_indexes = list(slots[0][2])
    previous_evidence = slots[0][3]
    for start, end, indexes, evidence in slots[1:]:
        if _evidence_distance(previous_evidence, evidence) >= change_threshold:
            region_scores = np.mean(similarities[:, region_indexes], axis=1)
            regions.append((region_start, start, region_scores))
            region_start = start
            region_indexes = []
        region_indexes.extend(indexes)
        previous_evidence = evidence
    regions.append((region_start, slots[-1][1], np.mean(similarities[:, region_indexes], axis=1)))
    return regions


def _transition_bonus(previous: str, current: str, bonus: float = 0.015) -> float:
    """Give circle-of-fifths resolution a small preference, never a veto."""
    previous_chord = parse_chord(previous)
    current_chord = parse_chord(current)
    if previous_chord and current_chord and (previous_chord[1] + 5) % 12 == current_chord[1]:
        return bonus
    return 0.0


def _decode_region_sequence(
    regions: list[tuple[float, float, np.ndarray]],
    labels: list[str],
    key: str,
    mode: str,
    config: ChordDecoderConfig | None = None,
) -> list[tuple[float, float, str, float]]:
    """Decode a stable maj/min/N.C. path over pre-detected regions."""
    if not regions:
        return []
    config = config or ChordDecoderConfig()
    chord_indices = [index for index, label in enumerate(labels) if label != "N"]
    nc_index = labels.index("N")
    emissions: list[np.ndarray] = []
    for _, _, scores in regions:
        values = np.asarray(scores, dtype=float).copy()
        best_chord = max(float(values[index]) for index in chord_indices)
        values[nc_index] = max(0.0, config.no_chord_threshold * 2 - best_chord)
        for index in chord_indices:
            values[index] += tonal_bias(labels[index], key, mode) * config.tonal_prior_scale
        emissions.append(values)

    path_scores = emissions[0].copy()
    backpointers: list[np.ndarray] = []
    for region_index in range(1, len(regions)):
        start, end, _ = regions[region_index]
        duration = max(0.0, end - start)
        # A new label needs more evidence when it would create a brief event.
        change_penalty = config.base_change_penalty + config.short_event_change_penalty * max(0.0, 1.0 - min(duration, 1.0))
        next_scores = np.full(len(labels), -np.inf)
        pointers = np.zeros(len(labels), dtype=int)
        for current_index, current_label in enumerate(labels):
            candidates = path_scores.copy()
            for previous_index, previous_label in enumerate(labels):
                if previous_index != current_index:
                    candidates[previous_index] -= change_penalty
                    candidates[previous_index] += _transition_bonus(previous_label, current_label, config.circle_fifths_bonus)
            best_previous = int(np.argmax(candidates))
            next_scores[current_index] = candidates[best_previous] + emissions[region_index][current_index]
            pointers[current_index] = best_previous
        path_scores = next_scores
        backpointers.append(pointers)

    state = int(np.argmax(path_scores))
    states = [state]
    for pointers in reversed(backpointers):
        state = int(pointers[state])
        states.append(state)
    states.reverse()

    decoded: list[tuple[float, float, str, float]] = []
    for (start, end, _), state, emission in zip(regions, states, emissions):
        label = labels[state]
        alternatives = np.delete(emission, state)
        margin = float(emission[state] - np.max(alternatives)) if len(alternatives) else float(emission[state])
        confidence = max(0.05, min(0.95, 0.45 + margin))
        decoded.append((start, end, label, confidence))
    return decoded


def _attach_region_candidates(
    events: list[ChordEvent],
    regions: list[tuple[float, float, np.ndarray]],
    labels: list[str],
    config: ChordDecoderConfig,
    limit: int = 3,
) -> list[ChordEvent]:
    """Attach raw regional alternatives separately from decoder priors."""
    nc_index = labels.index("N")
    chord_indices = [index for index, label in enumerate(labels) if label != "N"]
    for event in events:
        weighted_scores = np.zeros(len(labels), dtype=float)
        total_weight = 0.0
        for start, end, scores in regions:
            overlap = min(event.end, end) - max(event.start, start)
            if overlap > 0:
                weighted_scores += np.asarray(scores, dtype=float) * overlap
                total_weight += overlap
        if total_weight <= 0:
            continue
        weighted_scores /= total_weight
        best_chord = max(float(weighted_scores[index]) for index in chord_indices)
        weighted_scores[nc_index] = max(0.0, config.no_chord_threshold * 2 - best_chord)
        ordered = [int(index) for index in np.argsort(weighted_scores)[::-1]]
        selected_index = labels.index(event.symbol)
        retained = ordered[:limit]
        if selected_index not in retained:
            retained.append(selected_index)
        event.label_candidates = [
            ChordLabelCandidate(
                label=labels[index],
                score=round(max(0.0, min(1.0, float(weighted_scores[index]))), 4),
                acoustic_rank=ordered.index(index) + 1,
                decoder_selected=index == selected_index,
            )
            for index in retained
        ]
    return events


def decode_beat_synchronous_chords(
    similarities: np.ndarray,
    frame_times: np.ndarray,
    beats: BeatAnalysis,
    duration_seconds: float,
    labels: list[str],
    config: ChordDecoderConfig | None = None,
    *,
    preserve_regions: bool = False,
) -> list[ChordEvent]:
    """Detect beat-constrained harmonic regions, then assign chord labels."""
    config = config or ChordDecoderConfig()
    boundaries = [0.0]
    boundaries.extend(beat.time for beat in beats.beats if 0.02 < beat.time < duration_seconds - 0.02)
    if len(beats.beats) < 2:
        boundaries.extend(float(time) for time in frame_times if 0 < time < duration_seconds)
    boundaries.append(duration_seconds)
    boundaries = sorted(set(boundaries))
    regions = _detect_harmonic_regions(similarities, frame_times, boundaries, config.change_threshold)
    preliminary: list[tuple[float, float, str, float]] = []
    for start, end, scores in regions:
        best_index = int(np.argmax(scores))
        ordered = np.sort(scores)
        best = float(ordered[-1])
        margin = best - float(ordered[-2]) if len(ordered) > 1 else best
        label = "N" if best < config.no_chord_threshold else labels[best_index]
        confidence = max(0.05, min(0.95, 0.45 + margin))
        preliminary.append((float(start), float(end), label, confidence))
    key, mode = estimate_key_from_chords(_group_segments(preliminary))
    decoded = _decode_region_sequence(regions, labels, key, mode, config)
    events = [
        ChordEvent(id=f"region-{index + 1}", start=start, end=end, symbol=label, confidence=confidence)
        for index, (start, end, label, confidence) in enumerate(decoded)
    ] if preserve_regions else _group_segments(decoded)
    return _attach_region_candidates(events, regions, labels, config)


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
    def __init__(self, decoder_config: ChordDecoderConfig | None = None):
        self.decoder_config = decoder_config or ChordDecoderConfig()

    @property
    def parameters(self) -> dict[str, float]:
        return self.decoder_config.parameters()

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
            
            times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=hop_length)
            
            raw_regions = decode_beat_synchronous_chords(
                similarities, times, beats, audio.duration_seconds, labels,
                self.decoder_config, preserve_regions=True,
            )
            events = [event.model_copy(deep=True) for event in raw_regions if event.symbol != "N"]

            key, mode = estimate_key_from_chords(events)
                
            return ChordAnalysis(
                chords=events,
                raw_regions=raw_regions,
                key=key,
                mode=mode,
                confidence=0.6,
                engine="chromagram",
                engine_version="1.4",
                parameters=self.parameters,
            )
            
        except Exception as e:
            logger.error(f"Chromagram analysis failed: {e}")
            raise RuntimeError(f"Chromagram analysis failed: {e}")
