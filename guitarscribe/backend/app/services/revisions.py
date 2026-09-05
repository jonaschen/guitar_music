import uuid
from pathlib import Path

from ..models.score import SongScore


class RevisionStore:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, score: SongScore, revision_id: str | None = None) -> str:
        resolved_id = revision_id or str(uuid.uuid4())
        output_path = self.root_dir / f"{resolved_id}.json"
        output_path.write_text(score.model_dump_json(indent=2))
        return resolved_id

    def load(self, revision_id: str) -> SongScore:
        input_path = self.root_dir / f"{revision_id}.json"
        if not input_path.exists():
            raise FileNotFoundError(f"Revision not found: {revision_id}")
        return SongScore.model_validate_json(input_path.read_text())
