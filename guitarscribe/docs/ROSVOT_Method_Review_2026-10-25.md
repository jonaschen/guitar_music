# Codex：ROSVOT bounded method review — 2026-10-25

Scope: independent review of one candidate, ROSVOT. Official pages and source were inspected through the browser; no repository, weights, dependencies, or audio were downloaded or installed by this review. No inference was executed by the reviewer. Main owns implementation and experiments; the later results-review section independently inspects its generated artifacts. Links below refer to upstream `main` as observed today, not an immutable checkout; main must record the actual commit, configuration, and artifact hashes.

## Decision and early blockers

ROSVOT is a plausible bounded experiment because it learns note boundaries and note pitches from audio features rather than smoothing G's semitone contour. Proceed only as an experimental candidate. There is no evidence here that it improves our three songs, preserves repeated notes, or meets acceptable listening quality.

The stock inference entry point is **not CPU-ready**: `run_worker` constructs `cuda:rank` and calls `move_to_cuda` even in the single-worker path. CPU needs an explicit portability change, not merely an empty `CUDA_VISIBLE_DEVICES`. Models, mel processing, RMVPE, nested batch tensors, and checkpoint loading all need verification. No CPU runtime or memory benchmark was found in the reviewed official instructions; practical feasibility remains unmeasured. A short smoke inference should precede any full clip batch. [Official inference source](https://github.com/RickyL-2000/ROSVOT/blob/main/inference/rosvot.py#L234-L265)

## Method and paper evidence

The paper uses Conformer/U-Net features, boundary segmentation, and an attention-based note pitch decoder. It conditions on F0 and word boundaries. Its principal AST training combines M4Singer with a separate 20.9-hour corpus; its released checkpoint therefore must not be assumed identical to that benchmark. Threshold changes alter granularity. Paper evaluation allows 50 ms onset error and offsets within max(50 ms, 20% duration); these scores do not establish our tighter source-timing fidelity. Sine/harmonic controls are outside the singing domain: success is an engineering check, failure diagnoses that control but cannot alone establish real singing quality. [Official paper, sections 3–4](https://arxiv.org/html/2405.09940v2)

## Distribution and inference requirements

The official README reports testing Python 3.9, Torch 2.1.1 and CUDA 11.8. Its inference dependencies include librosa, tqdm, matplotlib, PyYAML, pretty_midi, and pyworld. It distributes `checkpoints.zip` containing ROSVOT, RWBD, and RMVPE; the README says released checkpoints were trained on M4Singer only. Standalone waveform inference automatically predicts word boundaries. Do not inject reference word timing into the candidate when G has no equivalent oracle. [Official instructions](https://github.com/RickyL-2000/ROSVOT#dependencies), [official weight link](https://drive.google.com/file/d/1JNtNT37KiLq9uFQqHk7JFs-3trxd3bRh/view?usp=sharing)

The reviewed default YAML uses 24 kHz, hop 128 (5.333 ms), RMVPE pitch conditioning, 50–900 Hz F0 bounds, boundary gap 90 ms and reference gap 40 ms. It declares `min_note_dur: 80`; **a declared parameter is not proof of an inference deletion rule**. The CLI defaults boundary threshold to 0.85, overriding the YAML's 0.8. Freeze the effective checkpoint configuration and CLI values before comparing songs; do not silently substitute paper defaults. [Official configuration](https://github.com/RickyL-2000/ROSVOT/blob/main/configs/rosvot.yaml)

## What “raw notes” can mean here

Boundary decoding already contains peak selection, merges boundaries closer than its minimum gap, and inserts/snaps boundaries to word references. These operations occur before note pitch decoding. They can suppress rapid repeats or force syllable-associated splits. “No additional project smoothing” is an accurate possible description; “unprocessed acoustic onsets” is not. Preserve logits, decoded boundaries and effective settings where possible. [Official boundary decoder](https://github.com/RickyL-2000/ROSVOT/blob/main/modules/rosvot/rosvot.py#L14-L80)

With supplied word durations, the save path can additionally adjust intervals to word times and merge consecutive equal-pitch notes within a word. **That branch requires `not self.apply_rwbd`; ordinary predicted-RWBD single-wave inference does not execute it.** Do not blame same-pitch merging on that inactive branch. The helper's behavior is explicit. [Official interval/slur helpers](https://github.com/RickyL-2000/ROSVOT/blob/main/tasks/rosvot/rosvot_utils.py)

Save-path intervals otherwise come directly from frame boundaries in seconds. NPY retains pitch labels and segment durations, including silence labels; conversion must retain silent duration while omitting silence events. The optional boundary-logit NPY is saved only in the plotting branch. Record no-notes/skipped cases as failures, not successful empty output. [Official result writer](https://github.com/RickyL-2000/ROSVOT/blob/main/inference/rosvot.py#L346-L431)

The MIDI helper skips pitch-zero segments, rejects nonpositive durations, and writes each remaining interval with velocity 120. No beat-grid quantization appears in that helper; MIDI serialization still has tick precision. Preserve pre-MIDI seconds and independently compare decoded MIDI timing. Do not infer raw audio accuracy from export parity. [Official MIDI writer](https://github.com/RickyL-2000/ROSVOT/blob/main/utils/audio/pitch_utils.py#L143-L177)

## License and overlap limits

Repository software is MIT, copyright Ruiqi Li 2024, with notice preservation and warranty disclaimer. The reviewed license does not separately enumerate every checkpoint or training-data right. The README also includes a consent restriction concerning generation of someone's speech/singing; this transcription review does not establish terms for a future singing-generation feature. Do not relicense or redistribute weights based solely on this software-license observation. [Official license](https://github.com/RickyL-2000/ROSVOT/blob/main/LICENSE), [README disclaimer](https://github.com/RickyL-2000/ROSVOT#disclaimer)

M4Singer is the documented checkpoint training corpus, but this review has not obtained a complete checkpoint training manifest or audited auxiliary RMVPE/RWBD training provenance. Exact recording, song, singer, and melody overlap for our three sources is **unverified**. Different singers or recordings do not guarantee an unseen song. Check the actual manifest, not only the repository's configurable test prefixes; a train/test configuration is not proof of the released checkpoint's training membership. Until verified, call the three clips project checkpoints, not independently held-out unseen-song evidence. [Official M4Singer repository](https://github.com/M4Singer/M4Singer)

## Bounded evaluation contract proposed for main

Freeze one model bundle, one effective configuration, one CPU portability patch, and the preselected windows across all sources. Record audio SHA, crop origin and duration, resampling, runtime, RSS, implementation/config/weight hashes, all predicted notes and silence segments. Convert crop-relative seconds to source seconds exactly once. Feed audio only; keep reference notes and expected counts exclusively in evaluation.

Use synthetic controls to detect offsets, lost rests, repeated-note merges and short-note loss, reporting domain mismatch explicitly. Then run the same frozen candidate on the already selected real checkpoints, with G unchanged. Report missing/extra notes, pitch and boundary errors where independent labels exist, fragmentation, coverage, and time cost. Do not equate fewer notes, zero tiny notes, or compiler parity with quality. Preserve failures; no per-song threshold search, minimum-duration cleanup, beat snapping or selective pitch repair. One concentrated listening comparison is warranted only if engineering checks and the agreed real-source gate support it. This review recommends no production integration or quality claim.

## Local save-path follow-up

Main subsequently provided the local official checkout at `/home/jonas/.cache/guitarscribe-rosvot-evaluation/ROSVOT`, identified by main as revision prefix `3c8332bf`. Read-only inspection confirms the following parsing contract for the planned CPU batch-one, automatic-RWBD experiment:

- `apply_rwbd=True` bypasses both interval-to-supplied-word adjustment and `regulate_ill_slur`. Adjacent equal nonzero pitches must remain separate events. `note2words=None` is expected and does not mean RWBD was unused; RWBD already conditioned boundary decoding.
- Read `pitches` and `note_durs` as parallel arrays. Start a crop-relative cursor at zero; for **every** segment compute end = cursor + duration, optionally emit a note for nonzero pitch, then advance the cursor even for pitch zero. Zero is silence/unvoiced classification, not MIDI pitch zero to play. Dropping zero segments before accumulating durations shifts every subsequent onset.
- Labels are already absolute MIDI numbers. The local `PitchDecoder` maps predictions below `note_start=30` or above `note_num=85` to zero. Do not add 30 or interpret 85 as a count yielding an upper MIDI limit of 114. Zero labels can therefore also reflect out-of-range predictions, not independently verified acoustic silence.
- `boundary2Interval` starts at frame zero and ends the final interval at `len(boundaries)-1`. The total saved segment duration consequently reflects that frame endpoint, not necessarily exact waveform length. Preserve the returned duration and report the residual; do not stretch the final note to fill the WAV. Frame conversion is 128/24000 seconds in this bundle. Add the crop's source origin once, after parsing.
- `note_durs` are unrounded seconds. NPY reconstruction is preferable to importing MIDI as the primary event source; independently inspect MIDI for serialization parity. Save original zero segments and adjacent repeated notes in the audit artifact even if rendering emits only pitched notes.
- Searching local `modules/` and `inference/` found no `min_note_dur` use. The ROSVOT checkpoint configuration does not declare that key, although RWBD's configuration does. There is no demonstrated inference-time 80 ms note deletion in this path; actual active restrictions are boundary regulation and pitch-label masking. This qualifies the earlier general reference to minimum-duration settings.
- A nonempty array containing only zero labels passes the writer's initial nonempty check; the MIDI helper then returns without writing a MIDI. Treat this as an explicit all-silence result, distinct from a skipped item, missing artifact, crash, or successful pitched transcription. Validate array lengths, finite positive durations and finite integral labels before event conversion; report malformed output instead of repairing it.

Local files inspected: `inference/rosvot.py` (`save_result`, dataset frame lengths), `tasks/rosvot/rosvot_utils.py`, `utils/audio/pitch_utils.py`, `modules/rosvot/rosvot.py`, and both checkpoint configuration YAMLs. No cached source, model, configuration, or runtime files were changed by this review.

## Independent result/parser review

Reviewed the completed `output/evaluation/rosvot-checkpoint-2026-10-25/report.json`, its six input entries, emitted harmonic notes, independent references, `backend/scripts/evaluate_rosvot_checkpoint.py`, and its imported control gate. No inference or evaluator was rerun and no parameters were changed. Main reports CPU inference-loop time of 24.6 seconds, excluding extra model loading; this review did not independently measure elapsed time.

The parser correctly accumulates **all** segment durations, emits only nonzero pitches, retains consecutive equal-pitch events, and checks finite positive durations, integral labels, array lengths, audio hashes, and total span within one frame. It compares note pitches and onset/end seconds against independently parsed MIDI, requiring agreement within one MIDI tick. All six cases report parity, maximum observed error about 1.122 ms. This establishes serialization consistency only. The span comparison is a check, not an endpoint repair. Baseline differences are explicitly labeled `comparison_not_accuracy`; G is not ground truth. The report's real IDs are four windows from three source groups, not four independent songs; `live` is an inherited artifact ID, not verified recording-type provenance.

| Window | G notes | ROSVOT notes | ROSVOT under 100 ms | ROSVOT voiced seconds |
| --- | ---: | ---: | ---: | ---: |
| third-1 | 112 | 49 | 0 | 16.213 |
| third-2 | 109 | 55 | 0 | 17.589 |
| saved-G | 67 | 43 | 0 | 12.741 |
| live | 88 | 43 | 0 | 15.307 |

Fewer notes and zero sub-100 ms events do not demonstrate improvement; they are also compatible with merged notes. Model-only voiced spans are 1.12, 2.06, 1.20, and 1.43 seconds respectively on the report's 10 ms comparison grid, so listen for filled rests and excessive sustains as well as pitch and articulation.

The harmonic control **fails**, with 9 reference notes, 7 predictions, 3 strict matches, 6 unmatched references and 4 unmatched predictions. These strict unmatched counts include timing failures, not just physically absent pitches. Concrete discrepancies in the preserved predictions:

- Two C4 attacks at 0.5 and 1.0 seconds become one C4 from 0.464 to 1.514667 seconds; the repeated-note boundary is lost.
- E4 expected at 1.75 starts at 1.514667, extending through the preceding rest.
- The legitimate 75 ms F4 is **present**, from 2.965333 to 3.082667 seconds (117.333 ms), outside the stipulated 50–100 ms duration gate. Describing it as simply missed would be incorrect.
- D4 at 3.5–4.0 seconds is absent; A4 starts at 3.493333 instead of 4.0 seconds. G4 starts at 6.282667 instead of 6.5, again covering a reference rest.

The vibrato control passes its fixed 50 ms gate with one predicted note, onset error −31.333 ms and offset error +24 ms. This single pass does not offset the harmonic failure. Neither synthetic control proves vocal-domain performance.

**Decision:** the strict synthetic gate has not passed. An exploratory listening comparison of the three already fixed source groups is defensible solely to observe real-singing behavior under this known domain mismatch, provided main explicitly labels it exploratory, discloses the harmonic failures, preserves the existing candidate/settings/windows and includes both third-source windows without choosing the better one. It must not be presented as the gate-qualified acceptance session described above, a quality pass, a replacement for G, or evidence of generalization. If the workflow requires every synthetic control to pass before any listening, this result does not satisfy that workflow; it would require an explicit scope distinction, not a retroactive threshold change. No additional model or tuning is recommended by this review.
