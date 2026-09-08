import click
import asyncio
import logging
from pathlib import Path
import sys
import json
import uvicorn
from .core.config import Settings
from .core.pipeline import create_pipeline
from .models.audio import SourceRequest, SourceType
from .exporters.json_exporter import JsonScoreExporter
from .models.score import SongScore
from .evaluation.metrics import evaluate_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def _analyze(audio_file, output, melody_mode, chord_complexity, separate_vocals, verbose):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    try:
        settings = Settings.from_env()
        pipeline = create_pipeline(settings)
        
        request = SourceRequest(
            source_type=SourceType.LOCAL,
            path=Path(audio_file),
            rights_confirmed=True
        )
        
        score = await pipeline.run(request, {
            "melody_mode": melody_mode,
            "chord_complexity": chord_complexity,
            "separate_vocals": separate_vocals,
        })
        
        exporter = JsonScoreExporter()
        out_path = Path(output) if output else None
        json_str = exporter.export(score, out_path)
        
        if not output:
            print(json_str)
            
        print(f"\n--- Summary ---", file=sys.stderr)
        print(f"BPM: {score.analysis.bpm}", file=sys.stderr)
        print(f"Key: {score.analysis.key} {score.analysis.mode}", file=sys.stderr)
        print(f"Chords: {len(score.chords)}", file=sys.stderr)
        print(f"Melody Notes: {len(score.melody)}", file=sys.stderr)
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(1)

@click.group()
def main():
    """GuitarScribe - Song analysis for guitar practice."""
    pass

@main.command()
@click.argument('audio_file', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), default=None, help='Output JSON path')
@click.option('--melody-mode', type=click.Choice(['vocal', 'guitar', 'mix']), default='vocal')
@click.option('--chord-complexity', type=click.Choice(['simple', 'standard', 'full']), default='standard')
@click.option('--separate-vocals', is_flag=True, help='Isolate vocals before vocal melody analysis (requires Demucs).')
@click.option('--verbose', '-v', is_flag=True)
def analyze(audio_file, output, melody_mode, chord_complexity, separate_vocals, verbose):
    """Analyze an audio file and output SongScore JSON."""
    asyncio.run(_analyze(audio_file, output, melody_mode, chord_complexity, separate_vocals, verbose))


@main.command("evaluate")
@click.argument("score_file", type=click.Path(exists=True, path_type=Path))
@click.argument("annotation_file", type=click.Path(exists=True, path_type=Path))
@click.option("--max-bpm-relative-error", type=click.FloatRange(min=0), default=None, help="Fail if BPM relative error exceeds this value.")
@click.option("--min-beat-f-measure", type=click.FloatRange(min=0, max=1), default=None, help="Fail if beat F-measure is below this value.")
@click.option("--min-chord-symbol-recall", type=click.FloatRange(min=0, max=1), default=None, help="Fail if chord recall is below this value.")
@click.option("--min-melody-pitch-accuracy", type=click.FloatRange(min=0, max=1), default=None, help="Fail if melody pitch accuracy is below this value.")
def evaluate(
    score_file: Path,
    annotation_file: Path,
    max_bpm_relative_error: float | None,
    min_beat_f_measure: float | None,
    min_chord_symbol_recall: float | None,
    min_melody_pitch_accuracy: float | None,
):
    """Print golden-fixture metrics and optionally enforce quality thresholds."""
    score = SongScore.model_validate_json(score_file.read_text())
    annotation = json.loads(annotation_file.read_text())
    metrics = evaluate_score(score, annotation)
    click.echo(json.dumps(metrics, indent=2, sort_keys=True))
    failures = []
    if max_bpm_relative_error is not None and metrics["bpm_relative_error"] > max_bpm_relative_error:
        failures.append(f"bpm_relative_error {metrics['bpm_relative_error']} exceeds {max_bpm_relative_error}")
    if min_beat_f_measure is not None and metrics["beat_f_measure"] < min_beat_f_measure:
        failures.append(f"beat_f_measure {metrics['beat_f_measure']} is below {min_beat_f_measure}")
    if min_chord_symbol_recall is not None and metrics["chord_symbol_recall"] < min_chord_symbol_recall:
        failures.append(f"chord_symbol_recall {metrics['chord_symbol_recall']} is below {min_chord_symbol_recall}")
    if min_melody_pitch_accuracy is not None and metrics["melody_pitch_accuracy"] < min_melody_pitch_accuracy:
        failures.append(f"melody_pitch_accuracy {metrics['melody_pitch_accuracy']} is below {min_melody_pitch_accuracy}")
    if failures:
        raise click.ClickException("Golden quality gate failed: " + "; ".join(failures))


@main.command()
@click.option('--host', default='0.0.0.0', show_default=True)
@click.option('--port', default=8000, type=int, show_default=True)
@click.option('--reload', is_flag=True, help='Enable auto-reload for development')
def serve(host, port, reload):
    """Run the GuitarScribe API server."""
    uvicorn.run("app.api:app", host=host, port=port, reload=reload)
    
if __name__ == '__main__':
    main()
