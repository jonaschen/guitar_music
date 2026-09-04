import json
from pathlib import Path
from typing import Optional
from ..models.score import SongScore

class JsonScoreExporter:
    def export(self, score: SongScore, output_path: Optional[Path] = None) -> str:
        json_str = score.model_dump_json(indent=2)
        
        if output_path:
            output_path.write_text(json_str)
            
        return json_str
