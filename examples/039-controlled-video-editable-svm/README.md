# Controlled Video -> Editable SVM v0

This is the Phase 1 demonstrator. It turns the already-proven recovery chain into
one reproducible, human-readable command:

```text
original controlled AVI/FFV1 video
-> recovered structured animation (one ordinary SVM Document, 12 Tracks)
-> one explicit Track edit through normal authoring
-> changed re-render, with Target B and Camera provably unchanged
```

It is a packaging and orchestration slice. It adds no recovery semantics: it calls
S11D ingestion, the frozen S11A/S11B/S11C adapters, ordinary
Document/Revision authoring, `MotionEvaluator` and `SVGRenderer`.

## Command

```powershell
svm demo-phase1 --output-directory build/phase1-demo
```

Run from the repository root. Equivalent module form:

```powershell
python -m svm.cli demo-phase1 --output-directory build/phase1-demo
```

The output directory must not already exist. Pass `--replace` to explicitly
replace it. `--config` selects an alternative configuration locator; the default
is `examples/039-controlled-video-editable-svm/config/phase1-demo.json`.

Output publication has a separate safety contract, including with `--replace`:

- Canonical path containment rejects the repository root and its ancestors,
  the current working directory and its ancestors, filesystem/drive roots,
  and any overlap with the repository's `examples` tree or configured input
  directories. Directory identity checks also cover Windows namespace/drive
  aliases. A normal `build/phase1-demo` output is allowed.
- Output paths and their existing ancestors must not be symbolic links or
  Windows reparse points (including junctions). Unresolvable or inaccessible
  paths fail closed with `DemoError`, reported by the CLI as exit code 2.
- Configuration, input locations and output safety are checked before creating
  a private staging directory in the output's parent. All recovery, editing,
  rendering, validation and bundle writes finish there before publication.
- For replacement, the completed staging bundle is published by first renaming
  the old output into a private backup, then renaming the new bundle to output.
  If the second rename fails, the old directory is restored. Failed staging
  leaves the old output byte-identical and removes the incomplete staging tree.

Replacing a nonempty directory is not a single atomic rename on all supported
platforms: readers may briefly see no final directory between the two renames.
This is an exception rollback strategy, not a crash/power-loss transaction or
support for concurrent writers. If the filesystem also refuses rollback, the
original bundle is retained in the backup location reported by `DemoError`;
it is never deleted during failed publication. After publication commits, a
backup-cleanup failure emits a warning and retains the successfully published
bundle. Staging names and absolute paths never enter the report or bundle.

Recovery configuration requires at least one anchor and one target, distinct
roles, one distinct Group per target, increasing nonnegative integer ticks, a
positive integer timebase and complete explicit component selectors. Invalid
configuration fails at the orchestration boundary before authoring any Tracks.

The command prints the machine-readable report to stdout and returns exit code 2
with a JSON error object on stderr if any check fails.

## Inputs

The demo reuses the checked-in frozen fixtures. It copies nothing and generates no
video:

| Role | Locator |
| --- | --- |
| Source video | `examples/038-controlled-video-ingestion/scene.avi` |
| Registered Recovery Document | `examples/037-explicit-multi-object-raster-recovery/recovery-base.svm.json` |
| Explicit component selectors | `examples/037-explicit-multi-object-raster-recovery/selectors.json` |

`scene.avi` is a 15008-byte RIFF AVI with one FFV1 stream at 1200 x 900, exact FPS
1/1. Source indices 0, 1, 2, 3 map to ticks 0, 12, 24, 36 at 12 ticks/second. The
scene is two static asymmetric anchors, two independently moving asymmetric
targets and one shared pan/rotation/zoom Camera, with a Camera hold between
recovered ticks 12 and 24.

Anchor identities, Target identities, Motion Target Bindings and every per-tick
component selector are explicit configuration. Nothing is inferred from pixels.

## Output bundle

```text
<output>/
  config/phase1-demo.json          recovery configuration actually used
  source/scene.avi                 the real AVI input bytes
  source/video-manifest.json       verified Video manifest (occurrence join)
  frames/<sha256>.png              4 canonical raster frames, content-addressed
  documents/recovered.svm.json     recovered Document, 12 Tracks
  documents/edited.svm.json        edited Document, separate Revision
  rendered/recovered/tick_0NN.svg  4 recovered snapshots
  rendered/edited/tick_0NN.svg     4 edited snapshots
  report.json                      machine-readable report
```

The recovered Document alone is not a complete archival package. Keep
`source/video-manifest.json` with it: the manifest joins each canonical PNG
Artifact ID to its Video occurrence and tick, which is how a recovered Track is
traced back to the source video.

## Recovered 12 Tracks

Target A and Target B each own `translate.x`, `translate.y`, `rotation_degrees`
and `scale`. The Camera owns `position.x`, `position.y`, `rotation_degrees` and
`scale`. Every Track carries four Keyframes at ticks 0, 12, 24 and 36.

Recovered values at ticks 0 / 12 / 24 / 36:

| Role | Property | 0 | 12 | 24 | 36 |
| --- | --- | ---: | ---: | ---: | ---: |
| Target A | translate.x | 0 | 7.839923 | 15.863733 | 24.086259 |
| Target A | translate.y | 0 | -4.601105 | -8.664911 | -12.185206 |
| Target A | rotation_degrees | 0 | 3.914082 | 7.933250 | 11.981756 |
| Target A | scale | 1 | 1.039489 | 1.076837 | 1.018446 |
| Target B | translate.x | 0 | -6.078668 | -12.712865 | -20.167340 |
| Target B | translate.y | 0 | -7.996312 | -14.232481 | -19.280044 |
| Target B | rotation_degrees | 0 | -3.052705 | -6.973180 | -10.918183 |
| Target B | scale | 1 | 0.979128 | 1.028244 | 1.009650 |
| Camera | position.x | 0 | 5.595961 | 5.595961 | 12.078516 |
| Camera | position.y | 0 | -3.523531 | -3.523531 | -7.023590 |
| Camera | rotation_degrees | 0 | 1.922118 | 1.922118 | 3.998905 |
| Camera | scale | 1 | 1.025977 | 1.025977 | 1.050436 |

Changing one Camera array position, rotation or scale value changes the whole
scene, which is why the two Targets are recovered by camera compensation rather
than absolute motion. `report.json` carries the full content-addressed Track IDs.

## The explicit edit

One ordinary supported SVM edit, applied through `RevisionStore.commit` with a
`SetKeyframeValueChange` inside an atomic `Transaction`. No JSON is mutated
directly and no demo-only Track format exists.

| Field | Value |
| --- | --- |
| Target | `entity:target-a` (group `group:1111...`) |
| Property | `rotation_degrees` |
| Tick | 12 |
| Before | 3.914081844 |
| After | 8.914081844 |
| Delta | +5.0 |

The recovered state is one Revision; the edited state is its child Revision with
its own `revision_id` and `document_hash`.

## Editability proof

`report.json` records these assertions; the command fails if any is false.

| Check | Result |
| --- | --- |
| Track count | 12 recovered, 12 edited |
| Changed ticks | `["12"]` |
| Re-rendered SVG changed ticks | `["12"]` |
| Target B unchanged | true |
| Camera unchanged | true |
| Target A other Track properties unchanged | true |

Because the edited Keyframe sits at tick 12 and interpolation is linear, only
tick 12 changes; ticks 0, 24 and 36 re-render byte-identically. Target A's group
transform at tick 12 moves from `rotation 3.914082` to `8.914082`, and the
re-rendered `tick_012.svg` differs accordingly.

## Determinism

Running the command twice from the same repository state produces byte-identical
output. All 18 bundle files hash identically across runs, including the report.

Semantic output contains no wall-clock timestamps, temporary paths, random
filenames or random identifiers. Frame files are named by content hash; Documents
carry deterministic Revision IDs; the demo transaction ID and message are fixed.
The bundle records no machine-specific absolute path.

## Ground Truth independence

The demo never reads `ground-truth.json` or `verification.json`. Numerical
Ground Truth error metrics remain available to the repository acceptance tests
(`tests/test_multi_object_raster_recovery.py`, `tests/test_video_recovery.py`) as
a post-hoc fixture validation, but the human-facing demo command does not depend
on them.

## Validation

```powershell
python -m unittest discover -s tests -p test_phase1_demo.py -v
```

`tests/test_phase1_demo.py` invokes the same production entry point as the
documented command and checks that the AVI is the real starting input, that
recovery returns 12 Tracks, that the recovered Document is serializable, that the
edit commits as a new Revision, that Target A changes while Target B and the
Camera do not, that the demo runs without Ground Truth, that repeated execution is
byte-identical, and that replacing an existing output directory is explicit.

## Limitations

- This is **controlled video input only**. It is not arbitrary or natural video
  recovery, and no claim is made beyond the fixtures in this repository.
- The accepted subset is exactly one complete RIFF AVI container at most 32 MiB
  with a single FFV1 video stream, exact integer timing, no audio, no dropped
  frames, 256 frames / 16 megapixels per frame / 256 million total decoded pixels.
  Decoding fails closed; direction is never guessed and no backend fallback
  exists.
- Roles, component selectors, anchor identities and Target bindings are explicit
  configuration inputs. Automatic component association, object discovery,
  tracking, optical flow, occlusion recovery and scene-cut handling are out of
  scope.
- Decoded frames must be exact black/white gray or equal-channel BGR. Color,
  alpha and intermediate gray are rejected.
- Byte-exact decode reproducibility is expected only with the pinned
  `opencv-python-headless` 4.14.0.94 wheel. The runtime gates on the required
  decoder capability (`CAP_PROP_PTS`) rather than on a version string, and warns
  when the installed version differs from the recorded reference.
- The command reads repository fixtures, so it runs from a source checkout rather
  than from a wheel installed outside the repository.

## References

- `spec/59-deterministic-video-frame-ingestion.md` — video subset, timing, verification.
- `spec/58-explicit-multi-object-raster-recovery.md` — explicit multi-object recovery boundaries.
- `examples/038-controlled-video-ingestion/README.md` — AVI fixture provenance and canonical frame digests.
- `examples/037-explicit-multi-object-raster-recovery/README.md` — recovered accuracy and Ground Truth.
- `svm/recovery_orchestration.py` — the thin production orchestration boundary.
- `svm/phase1_demo.py` — the demo runner, bundle and report.
