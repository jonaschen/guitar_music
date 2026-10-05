"""Read-only deployment smoke: synthetic score, no jobs/revisions persisted."""
import argparse
import json
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from app.models.score import SongScore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    score = SongScore.model_validate({
        "song": {"duration_seconds": 4},
        "beats": [{"time": time, "beat": i % 4 + 1, "measure": i // 4 + 1}
                  for i, time in enumerate([0, .6, 1.2, 1.8, 2.4, 2.8, 3.2, 3.6])],
        "melody": [{"id": "smoke-n", "start": 0, "end": .9, "midi": 60,
                    "note": "C4", "string": 2, "fret": 1}],
        "chords": [{"id": "smoke-c", "start": 0, "end": 1.2, "symbol": "C"},
                   {"id": "smoke-g", "start": 1.2, "end": 4, "symbol": "G"}],
    })
    payload = score.model_dump_json().encode()
    def post(endpoint):
        with urlopen(Request(args.base_url + endpoint, data=payload,
                             headers={"Content-Type": "application/json"}), timeout=30) as response:
            return response.read()
    with urlopen(args.base_url + "/health", timeout=30) as response:
        assert response.status == 200
    root = ElementTree.fromstring(post("/scores/musicxml"))
    attributes = root.find(".//attributes")
    assert attributes.findtext("staff-details/staff-tuning/tuning-octave") == "2"
    first = root.find(".//note[pitch]")
    assert first.findtext("type") == "quarter" and len(first.findall("dot")) == 1
    harmonies = root.findall(".//harmony")
    assert [h.findtext("root/root-step") for h in harmonies] == ["C", "G"]
    assert all(h.findtext("offset") == "0" for h in harmonies)
    manifest = json.loads(post("/scores/playback/manifest"))
    notes = [e for e in manifest["events"] if e["track"] == "melody"]
    assert [(n["start"], n["end"]) for n in notes] == [(0, .9)]
    assert post("/scores/midi").startswith(b"MThd")
    print("PASS deployed health, MusicXML tuning/dots/chords, unchanged melody timing, MIDI header")


if __name__ == "__main__":
    main()
