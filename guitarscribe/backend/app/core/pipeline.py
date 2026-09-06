import logging
from typing import Awaitable, Callable, Dict, Any
from ..models.audio import SourceRequest
from ..models.score import SongScore, SongInfo, AnalysisSummary, Provenance, KeyContext, KeySignature
from ..models.analysis import AudioFeatures, MelodyAnalysis, MelodyMode, ChordComplexity
from .config import Settings, ChordEngine
from ..analyzers.preprocessor import DemucsMelodySeparator, FFmpegPreprocessor
from ..analyzers.beats.librosa_beats import LibrosaBeatAnalyzer
from ..analyzers.chords.chromagram import ChromagramChordAnalyzer
from ..analyzers.chords.chordino import ChordinoChordAnalyzer
from ..analyzers.melody.basic_pitch_adapter import BasicPitchMelodyAnalyzer
from ..postprocess.chords import ChordPostProcessor
from ..postprocess.melody import MelodyPostProcessor
from ..postprocess.rhythm import RhythmSuggester
from ..fretboard.mapper import SimpleFretboardMapper
from ..sources.local import LocalAudioSource

logger = logging.getLogger(__name__)

class AnalysisPipeline:
    def __init__(self, preprocessor, beat_analyzer, chord_analyzer, melody_analyzer, chord_post, melody_post, rhythm_suggester, fretboard_mapper, source, melody_separator=None, max_duration_seconds: int = 600):
        self.preprocessor = preprocessor
        self.beat_analyzer = beat_analyzer
        self.chord_analyzer = chord_analyzer
        self.melody_analyzer = melody_analyzer
        self.chord_post = chord_post
        self.melody_post = melody_post
        self.rhythm_suggester = rhythm_suggester
        self.fretboard_mapper = fretboard_mapper
        self.source = source
        self.melody_separator = melody_separator
        self.max_duration_seconds = max_duration_seconds

    async def run(
        self,
        source_request: SourceRequest,
        options: Dict[str, Any],
        progress_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> SongScore:
        logger.info("Starting analysis pipeline")

        async def report(stage: str) -> None:
            if progress_callback:
                await progress_callback(stage)

        await report("resolving")
        
        asset = await self.source.fetch(source_request)
        await report("preprocessing")
        normalized = await self.preprocessor.normalize(asset)
        if normalized.duration_seconds > self.max_duration_seconds:
            raise ValueError(f"Audio duration exceeds the configured limit of {self.max_duration_seconds} seconds")
        
        await report("beat_analysis")
        beats = await self.beat_analyzer.analyze(normalized)
        
        await report("chord_analysis")
        chords = await self.chord_analyzer.analyze(normalized, beats)
        complexity = ChordComplexity(options.get("chord_complexity", "standard"))
        chords.chords = self.chord_post.process(chords.chords, beats, complexity)
        
        try:
            await report("melody_analysis")
            melody_mode = MelodyMode(options.get("melody_mode", "vocal"))
            separate_vocals = bool(options.get("separate_vocals", False))
            melody_audio = normalized
            source_separated = False
            separation_warnings: list[str] = []
            if separate_vocals and self.melody_separator and melody_mode == MelodyMode.VOCAL:
                try:
                    melody_audio, source_separated = await self.melody_separator.separate(normalized, melody_mode)
                except Exception as separation_error:
                    logger.warning("Vocal separation failed; using full mix: %s", separation_error)
                    separation_warnings.append(f"Vocal separation failed; using full mix: {separation_error}")
            elif separate_vocals and melody_mode == MelodyMode.VOCAL:
                separation_warnings.append("Vocal isolation was requested but is not enabled on this server; using the full mix.")
            melody = await self.melody_analyzer.analyze(melody_audio, beats, melody_mode)
            melody.notes = self.melody_post.process(melody.notes, beats.beats, melody_mode)
            melody = self.fretboard_mapper.map_notes(melody)
            melody.confidence, quality_warnings = self.melody_post.assess_quality(
                melody.notes, normalized.duration_seconds, melody_mode, source_separated=source_separated
            )
            melody.warnings.extend(warning for warning in [*separation_warnings, *quality_warnings] if warning not in melody.warnings)
        except Exception as e:
            logger.warning(f"Melody analysis failed, continuing without melody: {e}")
            melody = MelodyAnalysis(warnings=[str(e)])
            
        await report("postprocessing")
        rhythm = self.rhythm_suggester.suggest(beats, chords)
        
        return SongScore(
            song=SongInfo(
                title=asset.title,
                source_type=asset.source_type.value,
                duration_seconds=normalized.duration_seconds
            ),
            analysis=AnalysisSummary(
                key=chords.key,
                mode=chords.mode,
                bpm=beats.bpm,
                time_signature=beats.time_signature,
                warnings=[*beats.warnings, *chords.warnings, *melody.warnings],
            ),
            key_context=KeyContext(
                source=KeySignature(key=chords.key, mode=chords.mode),
                target=KeySignature(key=chords.key, mode=chords.mode),
                shape=KeySignature(key=chords.key, mode=chords.mode),
                sounding=KeySignature(key=chords.key, mode=chords.mode),
            ),
            beats=beats.beats,
            chords=chords.chords,
            melody=melody.notes,
            rhythm=rhythm,
            provenance=Provenance(
                beat_engine=beats.engine,
                chord_engine=chords.engine,
                melody_engine=melody.engine
            )
        )

def create_pipeline(settings: Settings) -> AnalysisPipeline:
    preprocessor = FFmpegPreprocessor(ffmpeg_binary=settings.ffmpeg_binary)
    beat_analyzer = LibrosaBeatAnalyzer()
    
    chord_analyzer = None
    if settings.chord_engine in (ChordEngine.AUTO, ChordEngine.CHORDINO):
        try:
            import vamp
            chord_analyzer = ChordinoChordAnalyzer()
            logger.info("Using Chordino for chord analysis")
        except Exception as e:
            if settings.chord_engine == ChordEngine.CHORDINO:
                raise
            logger.info("Falling back to Chromagram for chord analysis")
            
    if chord_analyzer is None:
        chord_analyzer = ChromagramChordAnalyzer()
        
    melody_analyzer = BasicPitchMelodyAnalyzer()
    
    chord_post = ChordPostProcessor()
    melody_post = MelodyPostProcessor()
    rhythm_suggester = RhythmSuggester(settings.rhythm_patterns_dir)
    fretboard_mapper = SimpleFretboardMapper()
    source = LocalAudioSource()
    melody_separator = DemucsMelodySeparator(settings.demucs_binary) if settings.melody_separator == "demucs" else None
    
    return AnalysisPipeline(
        preprocessor, beat_analyzer, chord_analyzer, melody_analyzer,
        chord_post, melody_post, rhythm_suggester, fretboard_mapper, source, melody_separator,
        max_duration_seconds=settings.max_duration_seconds
    )
