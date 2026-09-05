import re

from ..models.analysis import ChordVoicing


# Low-position standard-tuning shapes, ordered E-A-D-G-B-E.
COMMON_VOICINGS: dict[str, list[dict]] = {
    "C": [{"id": "open-c", "frets": [None, 3, 2, 0, 1, 0], "fingers": [None, 3, 2, None, 1, None], "difficulty": 1.0, "tags": ["open", "beginner"]}, {"id": "barre-c-3", "frets": [None, 3, 5, 5, 5, 3], "fingers": [None, 1, 3, 3, 3, 1], "base_fret": 3, "difficulty": 3.0, "tags": ["barre", "movable"]}],
    "D": [{"id": "open-d", "frets": [None, None, 0, 2, 3, 2], "fingers": [None, None, None, 1, 3, 2], "difficulty": 1.0, "tags": ["open", "beginner"]}, {"id": "barre-d-5", "frets": [None, 5, 7, 7, 7, 5], "fingers": [None, 1, 3, 3, 3, 1], "base_fret": 5, "difficulty": 3.0, "tags": ["barre", "movable"]}],
    "E": [{"id": "open-e", "frets": [0, 2, 2, 1, 0, 0], "fingers": [None, 2, 3, 1, None, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "G": [{"id": "open-g", "frets": [3, 2, 0, 0, 0, 3], "fingers": [2, 1, None, None, None, 3], "difficulty": 1.0, "tags": ["open", "beginner"]}, {"id": "barre-g-3", "frets": [3, 5, 5, 4, 3, 3], "fingers": [1, 3, 4, 2, 1, 1], "base_fret": 3, "difficulty": 3.0, "tags": ["barre", "movable"]}],
    "A": [{"id": "open-a", "frets": [None, 0, 2, 2, 2, 0], "fingers": [None, None, 1, 2, 3, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "Am": [{"id": "open-am", "frets": [None, 0, 2, 2, 1, 0], "fingers": [None, None, 2, 3, 1, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "Em": [{"id": "open-em", "frets": [0, 2, 2, 0, 0, 0], "fingers": [None, 2, 3, None, None, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "Dm": [{"id": "open-dm", "frets": [None, None, 0, 2, 3, 1], "fingers": [None, None, None, 2, 3, 1], "difficulty": 1.0, "tags": ["open", "beginner"]}],
}


ROOT_PITCH = {"C": 8, "C#": 9, "Db": 9, "D": 10, "D#": 11, "Eb": 11, "E": 0, "F": 1, "F#": 2, "Gb": 2, "G": 3, "G#": 4, "Ab": 4, "A": 5, "A#": 6, "Bb": 6, "B": 7}
ROOT_RE = re.compile(r"^([A-G](?:#|b)?)")
TRIAD_RE = re.compile(r"^([A-G](?:#|b)?)(m)?$")

class ChordVoicingProvider:
    def _closed_shapes(self, symbol: str) -> list[dict]:
        match = TRIAD_RE.match(symbol)
        if not match:
            return []
        root, minor = match.groups()
        low_e = ROOT_PITCH[root] or 12
        a_string = (ROOT_PITCH[root] - 5) % 12 or 12
        suffix = "minor" if minor else "major"
        return [
            {"id": f"closed-e-{suffix}-{root}", "frets": [low_e, low_e + 2, low_e + 2, low_e + (0 if minor else 1), low_e, low_e], "fingers": [1, 3, 4, 2 if not minor else 1, 1, 1], "base_fret": low_e, "difficulty": 3.5, "tags": ["closed", "barre", "movable", "e-shape"]},
            {"id": f"closed-a-{suffix}-{root}", "frets": [None, a_string, a_string + 2, a_string + 2, a_string + (1 if minor else 2), a_string], "fingers": [None, 1, 3, 4, 2 if minor else 3, 1], "base_fret": a_string, "difficulty": 3.5, "tags": ["closed", "barre", "movable", "a-shape"]},
        ]

    def get(self, symbol: str, capo: int = 0, max_fret: int = 15) -> list[ChordVoicing]:
        shapes = COMMON_VOICINGS.get(symbol, []) + self._closed_shapes(symbol)
        voicings = [
            ChordVoicing(
                id=shape["id"], symbol=symbol, shape_symbol=symbol, frets=shape["frets"],
                fingers=shape["fingers"], base_fret=shape.get("base_fret", 1), capo=capo, difficulty=shape["difficulty"], tags=shape["tags"],
            )
            for shape in shapes
            if max(fret for fret in shape["frets"] if fret is not None) <= max_fret
        ]
        if voicings:
            return voicings
        root = ROOT_RE.match(symbol)
        fret = ROOT_PITCH.get(root.group(1)) if root else None
        if fret is None or fret > max_fret:
            return []
        return [ChordVoicing(id=f"root-note-{symbol}", symbol=symbol, shape_symbol=symbol, frets=[fret, None, None, None, None, None], fingers=[1, None, None, None, None, None], base_fret=max(1, fret), capo=capo, difficulty=0.5, tags=["fallback", "root-note", "incomplete"])]
