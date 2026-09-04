import sys
from pathlib import Path

# Add backend to path to import conftest
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from tests.conftest import generate_test_audio

if __name__ == "__main__":
    audio_dir = Path(__file__).parent / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out_path = audio_dir / "test_progression.wav"
    
    generate_test_audio(out_path)
    print(f"Generated fixture at {out_path}")
