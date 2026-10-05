// Reads backend/scripts/musicxml_reader_fixtures.py JSON from stdin.
// Exercises the installed production reader without a backend server or user data.
import fs from "node:fs";
import assert from "node:assert/strict";
import { importer, Settings } from "@coderline/alphatab";

const cases = JSON.parse(fs.readFileSync(0, "utf8"));
assert.ok(cases.length > 0);
for (const fixture of cases) {
  const score = importer.ScoreLoader.loadScoreFromBytes(new TextEncoder().encode(fixture.xml), new Settings());
  const beats = score.tracks[0].staves[0].bars[0].voices[0].beats;
  const first = beats[0];
  if (fixture.chords) {
    const chords = beats.filter(b => b.chordId).map(b => [b.displayStart, b.voice.bar.staff.getChord(b.chordId).name]);
    assert.deepEqual(chords, fixture.chords, `${fixture.name}: timed chord changes`);
    assert.equal(beats.reduce((sum, beat) => sum + beat.displayDuration, 0), 3840);
    if (fixture.tied) {
      const notes = beats.flatMap(b => b.notes);
      assert.equal(notes.length, 2);
      assert.equal(notes[0].isTieOrigin, true);
      assert.equal(notes[1].isTieDestination, true);
    }
    console.log(`PASS ${fixture.name}: timed harmonies, sustain and measure duration`);
    continue;
  }
  assert.equal(first.dots, fixture.dots, `${fixture.name}: visible dots`);
  assert.equal(first.duration, fixture.duration, `${fixture.name}: visible note value`);
  assert.equal(first.displayDuration, fixture.ticks, `${fixture.name}: exact duration`);
  assert.equal(first.notes[0].fret, 1);
  // alphaTab string numbers count from the bass string; MusicXML counts from treble.
  assert.equal(first.notes[0].string, 5);
  assert.equal(first.notes[0].realValue, 60, `${fixture.name}: sounding pitch from TAB tuning`);
  assert.equal(beats.reduce((sum, beat) => sum + beat.displayDuration, 0), 3840);
  console.log(`PASS ${fixture.name}: dots, duration, TAB position, full measure`);
}
