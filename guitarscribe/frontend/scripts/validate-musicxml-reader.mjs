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
  assert.equal(first.dots, fixture.dots, `${fixture.name}: visible dots`);
  assert.equal(first.duration, fixture.duration, `${fixture.name}: visible note value`);
  assert.equal(first.displayDuration, fixture.ticks, `${fixture.name}: exact duration`);
  assert.equal(first.notes[0].fret, 1);
  // alphaTab string numbers count from the bass string; MusicXML counts from treble.
  assert.equal(first.notes[0].string, 5);
  assert.equal(beats.reduce((sum, beat) => sum + beat.displayDuration, 0), 3840);
  console.log(`PASS ${fixture.name}: dots, duration, TAB position, full measure`);
}
