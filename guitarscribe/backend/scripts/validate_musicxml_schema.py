"""Explicit compatibility check with a local official MusicXML 3.1 XSD bundle.

Run with lxml installed in an isolated validation environment:
PYTHONPATH=. python scripts/validate_musicxml_schema.py /path/to/schema
No downloads, production data access, or writes are performed by this script.
"""
import argparse
import hashlib
from pathlib import Path

from lxml import etree

from app.exporters.musicxml import export_musicxml
from app.models.score import SongScore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schema_dir", type=Path)
    args = parser.parse_args()
    directory = args.schema_dir.resolve()
    expected = {
        "musicxml.xsd": "49ae9e34e04ba5b72004687994f70d598323eb3353eadb62faedcc9e9dc4bd7f",
        "xml.xsd": "616a3077df5cfc954ac74a75abe9697b95eef7a85dbe09367d995a483e840eb5",
        "xlink.xsd": "67c7f7a02491babc51e11c10268150b1a76070da36d5abe88e68515009611966",
    }
    for name, digest in expected.items():
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if actual != digest:
            raise SystemExit(f"Unexpected MusicXML 3.1 schema bytes: {name} ({actual})")
        print(name, actual)

    class LocalResolver(etree.Resolver):
        def resolve(self, url, public_id, context):
            name = url.rsplit("/", 1)[-1]
            if name not in {"musicxml.xsd", "xml.xsd", "xlink.xsd"}:
                raise ValueError(f"Unexpected schema dependency: {url}")
            return self.resolve_filename(str(directory / name), context)

    xml_parser = etree.XMLParser(no_network=True, resolve_entities=False)
    xml_parser.resolvers.add(LocalResolver())
    schema = etree.XMLSchema(etree.parse(str(directory / "musicxml.xsd"), xml_parser))

    cases = {
        "empty": {},
        "tab-ties": {"song": {"duration_seconds": 6}, "melody": [
            {"id": "n", "start": 1.5, "end": 4.5, "midi": 64, "note": "E4", "string": 1, "fret": 0}]},
        "pickup": {"beats": [{"time": .5, "beat": 1, "measure": 1}], "melody": [
            {"id": "n", "start": .1, "end": .4, "midi": 60, "note": "C4"}]},
        "harmonies": {"song": {"duration_seconds": 6}, "chords": [
            {"id": str(i), "start": i * .5, "end": (i + 1) * .5, "symbol": symbol}
            for i, symbol in enumerate(["Bbmaj7/D", "F#m7/C#", "Ebsus4/Bb", "Bdim7", "Cm7b5", "G7", "N.C.", "C7alt"])]},
        "compound-grid": {"song": {"duration_seconds": 3}, "analysis": {"time_signature": "6/8"},
            "beats": [{"time": t, "beat": i + 1, "measure": 1} for i, t in enumerate([0, .3, .5, .8, 1, 1.3])]
                + [{"time": 1.5, "beat": 1, "measure": 2}],
            "melody": [{"id": "n", "start": .3, "end": 1.7, "midi": 66, "note": "F#4", "string": 1, "fret": 2}]},
    }
    failures = []
    for name, payload in cases.items():
        root = etree.fromstring(export_musicxml(SongScore.model_validate(payload)).encode(), xml_parser)
        if not schema.validate(root):
            failures.append(name)
            print(f"FAIL {name}: {schema.error_log}")
        else:
            print(f"PASS {name}")
    # Prove the verifier rejects an invalid document rather than merely parsing it.
    assert not schema.validate(etree.fromstring(b"<score-partwise><invalid/></score-partwise>"))
    if failures:
        raise SystemExit(f"Schema failures: {', '.join(failures)}")
    print(f"{len(cases)} valid exports; invalid control rejected")


if __name__ == "__main__":
    main()
