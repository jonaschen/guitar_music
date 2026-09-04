import click
import asyncio
import logging
from pathlib import Path
import sys
from .core.config import Settings
from .core.pipeline import create_pipeline
from .models.audio import SourceRequest, SourceType
from .exporters.json_exporter import JsonScoreExporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def _analyze(audio_file, output, melody_mode, chord_complexity, verbose):
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
            "chord_complexity": chord_complexity
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
@click.option('--verbose', '-v', is_flag=True)
def analyze(audio_file, output, melody_mode, chord_complexity, verbose):
    """Analyze an audio file and output SongScore JSON."""
    asyncio.run(_analyze(audio_file, output, melody_mode, chord_complexity, verbose))
    
if __name__ == '__main__':
    main()
