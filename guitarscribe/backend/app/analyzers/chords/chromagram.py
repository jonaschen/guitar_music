import logging
import numpy as np
import librosa
from collections import Counter
from ...models.audio import NormalizedAudio
from ...models.analysis import BeatAnalysis, ChordAnalysis, ChordEvent

logger = logging.getLogger(__name__)

ROOTS = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']

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
            
            events = []
            current_label = None
            start_time = 0.0
            chord_idx = 1
            
            for i, chord_id in enumerate(best_chords):
                label = labels[chord_id]
                t = times[i]
                
                if label != current_label:
                    if current_label is not None and current_label != "N":
                        events.append(ChordEvent(
                            id=f"chord-{chord_idx}",
                            start=float(start_time),
                            end=float(t),
                            symbol=current_label,
                            confidence=0.5
                        ))
                        chord_idx += 1
                    current_label = label
                    start_time = t
                    
            if current_label is not None and current_label != "N":
                events.append(ChordEvent(
                    id=f"chord-{chord_idx}",
                    start=float(start_time),
                    end=float(audio.duration_seconds),
                    symbol=current_label,
                    confidence=0.5
                ))
                
            key = "C"
            mode = "major"
            if events:
                counts = Counter(e.symbol for e in events)
                most_common = counts.most_common(1)[0][0]
                key = most_common.replace('m', '')
                mode = "minor" if most_common.endswith('m') else "major"
                
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
