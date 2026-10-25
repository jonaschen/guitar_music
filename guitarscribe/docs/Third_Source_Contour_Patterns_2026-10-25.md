# Third source: contour and G patterns

Date: 2026-10-25. This is a read-only engineering audit of the two listening windows already fixed at 20–40 s and 40–60 s. It does not select additional listening clips or infer a listening verdict.

## Source and timing

- Job: `f303ec8a86834633b060920fa85430af`, YouTube source `0rpbhqZI0hc`, completed with a 60-second analysis window and `source_start_seconds = 0`.
- The saved analysis score is in `output/work/jobs/f303ec8a86834633b060920fa85430af` in `jobs.sqlite3`; the corresponding G events are `output/evaluation/third-source-2026-10-25/G-score.json` (260 notes). The fixed rendered windows are `g-1.json` / `g-2.json`; their event times are local to their respective 20-second clips. The report records `compiler_parity: true`.
- Contour file: `output/work/jobs/f303ec8a86834633b060920fa85430af/melody-contour.json`, 2,584 frames, 23.21995 ms hop, source range 0–60 s. Its `source_artifact_sha256` identifies `vocal-stem.wav` (`b7fd25590abc742bbf93eadd9e38a6262c7b0ee635fddba780c099d3ee47994f`). Contour JSON SHA-256: `8a65c277a9a93db60dff808cf27e52f67cdebe3d0ec664504cdacbb87e37d2ba`. G-score SHA-256: `56d0ee001d6f2e1981060bd4c3544cfe7acbe4ca10c0b3ac9ca9750fab464d53`.
- The renderer's fixed-window report lists 112 G events in 20–40 s, 59 shorter than 100 ms and none shorter than 10 ms; 109 in 40–60 s, 57 shorter than 100 ms and none shorter than 10 ms. These are event-duration counts, not an error rate.

## Observations

### Short alternating G events

For this scan, an alternating fragment run means at least five consecutive G events, each shorter than 100 ms, with nonzero pitch changes of at most two semitones whose directions alternate up/down. This rule finds one run in the fixed windows:

| G time (s) | MIDI sequence | Durations (ms) |
|---|---|---|
| 30.1627–30.5110 | 51, 50, 51, 50, 51, 50 | 23.2, 23.2, 92.9, 92.9, 69.7, 46.4 |

The contour frames over the same interval do not form a stable two-bin semitone toggle. Rounded MIDI values move through approximately 51, 50, 50.5, 51, 51, 50.5, 50, 49.5, 49.5, 50, 51, 51, 51, 50, 49.5; voicing probabilities vary from 0.3 to 0.88. Thus the G event sequence is an observed segmentation pattern, while the frame track shows a changing and somewhat fluctuating pitch estimate over that interval.

### G leaps of at least seven semitones

The table lists adjacent G-event transitions with absolute pitch difference at least seven semitones. “Contour support” counts frames in the destination event with voiced probability at least 0.5; it describes the saved F0 track only.

| Destination onset (s) | MIDI transition | Difference | Destination duration | Contour support during destination |
|---:|---:|---:|---:|---|
| 22.8252 | 56 → 48 | −8 | 719.8 ms | 22 frames; median 48.0, range 47.5–48.5 |
| 25.2865 | 48 → 60 | +12 | 255.4 ms | 9 frames; median 60.0, range 60.0–60.5 |
| 27.8639 | 56 → 48 | −8 | 696.6 ms | 26 frames; median 48.0, range 47.5–48.5 |
| 37.6395 | 49 → 59 | +10 | 139.3 ms | 0 frames at probability ≥0.5 |
| 50.0854 | 56 → 72 | +16 | 139.3 ms | 2 frames; both at 72.0 |
| 50.9910 | 73 → 61 | −12 | 92.9 ms | 2 frames; both at 60.5 |
| 52.0127 | 53 → 60 | +7 | 185.8 ms | 5 frames; median 60.0, range 60.0–60.0 |

Only the two 56 → 48 transitions meet the ≥300 ms destination-duration criterion. In both, the saved contour stays near MIDI 48 through most of the destination interval. This agreement does not establish whether the note is musically correct, nor does the size of the preceding jump establish an octave error.

## Hypotheses and limits

- The six-event alternation around 30.16 s may be a segmentation of a quickly changing or uncertain contour. It is a useful engineering audit point, not evidence by itself of vibrato, a rearticulation, or six true notes.
- The two long 56 → 48 transitions are present in both G and the saved contour for most of their durations. They should not be labelled octave mistakes without independent pitch truth or listening evidence.
- The ≥7-semitone transitions after 40 s are all shorter than 300 ms. Their contour support is sparse or brief, so this scan cannot say whether they are errors, ornaments, or genuine transitions.
- The contour is only a model estimate, and voiced probability is not calibrated confidence in musical correctness. No truth-labelled pitch track was available here. Nothing in these counts classifies vibrato or true octave errors.

Method: read the job payload and JSON artifacts without modifying them; convert positive contour frequencies to continuous MIDI and inspect frames at the stored hop; count G event durations and adjacent MIDI differences from the fixed G-score. No model, browser, renderer, download, or database write was run for this note.
