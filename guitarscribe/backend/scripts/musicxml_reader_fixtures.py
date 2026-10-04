"""Emit synthetic exports for the frontend's installed alphaTab reader check."""
import json
from app.models.score import SongScore
from app.exporters.musicxml import export_musicxml


cases = []
for name, duration, dots, value in [("dotted-quarter", .75, 1, 4),
                                    ("double-dotted-quarter", .875, 2, 4),
                                    ("dotted-eighth", .375, 1, 8)]:
    score = SongScore.model_validate({
        "song": {"duration_seconds": 2}, "analysis": {"bpm": 120},
        "melody": [{"id": "n", "start": 0, "end": duration, "midi": 60,
                    "note": "C4", "string": 2, "fret": 1}],
    })
    cases.append({"name": name, "xml": export_musicxml(score), "dots": dots,
                  "duration": value, "ticks": round(duration * 1920)})
print(json.dumps(cases))
