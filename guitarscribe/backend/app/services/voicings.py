from ..models.analysis import ChordVoicing


# Low-position standard-tuning shapes, ordered E-A-D-G-B-E.
COMMON_VOICINGS: dict[str, list[dict]] = {
    "C": [{"id": "open-c", "frets": [None, 3, 2, 0, 1, 0], "fingers": [None, 3, 2, None, 1, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "D": [{"id": "open-d", "frets": [None, None, 0, 2, 3, 2], "fingers": [None, None, None, 1, 3, 2], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "E": [{"id": "open-e", "frets": [0, 2, 2, 1, 0, 0], "fingers": [None, 2, 3, 1, None, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "G": [{"id": "open-g", "frets": [3, 2, 0, 0, 0, 3], "fingers": [2, 1, None, None, None, 3], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "A": [{"id": "open-a", "frets": [None, 0, 2, 2, 2, 0], "fingers": [None, None, 1, 2, 3, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "Am": [{"id": "open-am", "frets": [None, 0, 2, 2, 1, 0], "fingers": [None, None, 2, 3, 1, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "Em": [{"id": "open-em", "frets": [0, 2, 2, 0, 0, 0], "fingers": [None, 2, 3, None, None, None], "difficulty": 1.0, "tags": ["open", "beginner"]}],
    "Dm": [{"id": "open-dm", "frets": [None, None, 0, 2, 3, 1], "fingers": [None, None, None, 2, 3, 1], "difficulty": 1.0, "tags": ["open", "beginner"]}],
}


class ChordVoicingProvider:
    def get(self, symbol: str, capo: int = 0, max_fret: int = 15) -> list[ChordVoicing]:
        shapes = COMMON_VOICINGS.get(symbol, [])
        return [
            ChordVoicing(
                id=shape["id"], symbol=symbol, shape_symbol=symbol, frets=shape["frets"],
                fingers=shape["fingers"], capo=capo, difficulty=shape["difficulty"], tags=shape["tags"],
            )
            for shape in shapes
            if max(fret for fret in shape["frets"] if fret is not None) <= max_fret
        ]
