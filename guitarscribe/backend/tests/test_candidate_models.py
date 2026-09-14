import pytest
from pydantic import ValidationError

from app.models.candidates import (
    AnalyzerRun,
    ChordCandidateRegion,
    ChordResult,
    MelodyCandidateNote,
    MelodyCandidateResult,
    TimingCandidate,
    TimingResult,
)


def test_canonical_candidate_results_preserve_engine_and_raw_artifact():
    run = AnalyzerRun(
        engine="candidate-engine",
        engine_version="1.2.3",
        parameters={"threshold": 0.4},
        raw_artifact="artifacts/run-1/raw.json",
    )

    timing = TimingResult(run=run, candidates=[TimingCandidate(bpm=120, beats=[0, 0.5])])
    chords = ChordResult(run=run, regions=[ChordCandidateRegion(start=0, end=1, label="Am")])
    melody = MelodyCandidateResult(
        run=run,
        source="instrument",
        notes=[MelodyCandidateNote(start=0, end=0.5, midi=69.2)],
    )

    assert timing.run.raw_artifact == "artifacts/run-1/raw.json"
    assert chords.regions[0].label == "Am"
    assert melody.notes[0].midi == 69.2


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ChordCandidateRegion, {"start": 1, "end": 1, "label": "C"}),
        (MelodyCandidateNote, {"start": 2, "end": 1, "midi": 60}),
    ],
)
def test_candidate_intervals_must_have_positive_duration(model, payload):
    with pytest.raises(ValidationError):
        model(**payload)
