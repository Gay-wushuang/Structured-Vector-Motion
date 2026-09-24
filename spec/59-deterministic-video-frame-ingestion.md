# Deterministic Video Frame Ingestion v0 (S11D)

Status: bounded input/evidence contract. No recovery, motion, Document, Change
authority or evaluation semantics change. Governing invariants: INV-REF-001/002,
INV-EVAL-002/003 and the explicit motion-target boundaries. S11A/B/C remain frozen.

## Supported container and decoder

The existing optional `analysis` dependency pins `opencv-python-headless` to
4.14.0.94 (OpenCV 4.14.0). Its bundled FFmpeg backend is selected explicitly with
`CAP_FFMPEG`; there is no backend fallback, external ffmpeg executable, new
dependency, streaming, network URL, webcam, audio processing or runtime encoding.

v0 accepts exactly one complete RIFF AVI container, at most 32 MiB, with one
FFV1 video stream. OpenDML/multiple RIFF segments, audio streams, other codecs and
containers, nested/interleaved frame packet layouts and empty/dropped packets
are outside the subset. Stream start must be zero, sample size variable, and
there must be exactly one nonempty `00dc` packet for each declared frame. AVI
header dimensions/count, stream dimensions/count and decoded dimensions/count
must agree. Limits are 256 frames, 16 megapixels per frame and 256 million total
decoded pixels. This is short controlled input, not a general AVI importer.

The small RIFF reader validates structural bounds, codec, dimensions and exact
integer timing metadata. It never decodes compressed pixels. OpenCV/FFmpeg owns
FFV1 decoding. Decode proceeds sequentially through the complete declared stream,
including unselected frames; seeking and backend frame numbers do not establish
identity. Any failed read, unexpected additional frame, changed dimensions or
non-CFR decoded PTS rejects the whole request. No previous-frame duplication,
interpolation, silent omission or renumbering is permitted. Structural truncation
and detected codec failures reject; this is not an authenticated container or a
claim to detect every possible bit corruption that still yields valid pixels.

Windows and Linux must run the same checked-in codec and canonical-output test
in the existing Python 3.11/3.12 quality matrix. There are no skips, alternate
codecs or platform-specific thresholds. The test logs actual FFmpeg library
versions and canonical frame hashes. Library builds may differ across wheels;
arbitrary compressed-video decode equivalence is NOT assumed. This policy's
claim is limited to exact controlled FFV1 input and verified canonical outputs.
A failed matrix cell blocks freezing this contract; do not silently substitute
a decoder or codec.

Upstream evidence: [OpenCV wheel packaging](https://github.com/opencv/opencv-python)
states that wheels bundle FFmpeg. [OpenCV video I/O properties](https://docs.opencv.org/4.x/d4/d15/group__videoio__flags__base.html)
define the FFmpeg PTS/FPS properties. Availability is tested with real container
bytes, not inferred solely from those documents or a reported codec name.

## Exact timing and explicit sampling

`VideoSampling` requires a nonempty, strictly increasing, unique tuple of source
frame indices and positive integer `ticks_per_second`. AVI `dwRate/dwScale`
defines a reduced rational source FPS. Optional caller `source_fps=(n,d)` is an
exact assertion against that header, never an override or inferred rational.

For source index i, using Fraction/integer arithmetic:

```text
source_timestamp = i * dwScale / dwRate
tick = source_timestamp * ticks_per_second
```

Every selected timestamp must map to an integer tick. Fractional ticks reject;
there is no rounding, accumulated floating-point time, wall clock or processing
speed dependency. The decoder's floating FPS is checked against the rational
header as a consistency check only. Decoded PTS must equal sequential index in
the FPS timebase; these small integer checks introduce no timing drift.

The scene fixture has exact FPS 1/1. Indices 0,1,2,3 at 12 ticks/second map to
ticks 0,12,24,36. An explicit subset (1,3) maps to (12,36), preserving indices.
The fractional fixture's actual AVI rate/scale is 2997/100: its writer rounded
the requested 30000/1001 before recording the file. At 2997 ticks/second its first
two frames map exactly to 0 and 100; declaring 30000/1001 is rejected. The API
does not claim those distinct rational frame rates are interchangeable.

## Canonical controlled raster frames

Policy identities:

- `svm-controlled-avi-ffv1-ingestion@0.1`
- `svm-exact-binary-gray8-video-frames@0.1`

Decoded samples must be uint8 grayscale, or three BGR channels that are exactly
equal at every pixel. Equal-channel projection is exact and involves no weighted
color conversion. Only values 0 and 255 are accepted. Color, alpha, intermediate
gray, other dtypes and invalid dimensions reject. There is no threshold cleanup,
denoise, morphology, segmentation or inference of foreground.

Canonical output reuses the existing SVM `_encode_mask_png` encoder unchanged:
8-bit opaque grayscale, filter-0 rows, stored DEFLATE and the existing deterministic
binary-mask text chunk. Original polarity is preserved; no foreground inversion
is performed. No second PNG encoder or grayscale conversion is introduced.
`canonical_reference_png` uses the existing PNG header checks and the same exact
pixel domain to independently canonicalize a reference PNG.

Decoded output equals canonicalized reference PNG bytes exactly. The original
S11C PNGs use a different compression encoding, so their raw Blob IDs differ.
This difference is explicit: pixel content, components, sampled transforms and
presented geometry remain equal. Normalizing both paths produces identical PNG
Artifact IDs and naturally identical downstream identities and Proposals.

## Identity, manifest and verification

The Video ReferenceArtifact is content-addressed independently of its frames.
Canonical PNG ReferenceArtifacts carry pixel content only, with empty provenance,
so existing Raster consumers need only the PNG and tick and remain video-agnostic.
They are immutable input snapshots, not accepted evaluated values. Equal pixels
have equal PNG bytes/Artifact IDs, including repeated frames and frames shared
between different containers. Do not put occurrence metadata into PNG bytes or
create conflicting per-occurrence descriptors for one PNG Blob.

Instead, a DerivedArtifact manifest records:

- the resolved Video reference (including hash and declared descriptor);
- exact source container/codec/dimensions/count/rational FPS;
- explicit sampling options and ticks_per_second;
- pinned decoder wheel/runtime/backend and canonicalization policies;
- each source frame index, reduced rational timestamp, tick, PNG Artifact ID and
  video-frame occurrence ID.

Occurrence IDs hash source Video ID, source index/timestamp, PNG ID, tick,
ticks_per_second and both policies. They include no temporary filename, byte
offset or backend-internal frame counter. Repeated frames share a PNG Blob but
have distinct video occurrences; downstream raster occurrences at distinct ticks
remain distinct under S10B/S11A semantics.

`verify_video_manifest` resolves the exact recorded Video reference, decodes it
again, reconstructs the canonical manifest and compares all recorded bytes,
policies, options, occurrence IDs, timestamps and frame content/descriptors.
Forged references, frame indices, timestamps, pixel associations and provenance
reject. A hash alone is not proof that a claimed derivation is true.

Ingestion imports no outputs until source validation and full decode succeed.
It has no RevisionStore, Proposal acceptance, Entity/Group creation, Track
authoring or automatic binding authority. Its manifest is an input-bundle sidecar,
not a Document mutation. Retain the source Video and manifest alongside the
recovered Document for complete provenance. Track -> accepted raster evidence
identifies (PNG ID, tick); joining that pair to the verified manifest identifies
the source video occurrence and Video Artifact. A Document alone retains its
existing PNG evidence but does not invent a missing container provenance link.

## API, CLI and executable proof

`svm.video_ingestion.ingest_video(repository, source_reference, VideoSampling(...))`
returns the manifest, canonical frames and occurrences. `verify_video_manifest`
is separately callable. No Document argument is accepted.

```powershell
svm ingest-video examples/038-controlled-video-ingestion/scene.avi `
  --frame-index 0 --frame-index 1 --frame-index 2 --frame-index 3 `
  --ticks-per-second 12 --source-fps 1/1 --output-directory video-input
```

CLI follows the existing JSON result/error convention. It requires a new output
directory and exports `source.avi`, `frame-manifest.json` and PNGs named by content
hash. All derivation checks finish before file export. Paths are locators only.

The video-only acceptance test blocks PNG and Ground Truth reads during ingestion
and recovery. It passes canonical frame bytes to the existing S11C test
orchestration through a small input-injection parameter, without copying or
altering production recovery. Four independent explicit lineages, two static
anchors, one shared Camera consensus, two bindings and A/B/Camera Tracks yield
one editable 12-Track Document. Only after recovery does it compare reference
paths and Ground Truth. Existing S11B tolerances remain unchanged. Camera holds
over 12..24 while both targets continue moving.

Negative tests cover unsupported container/codec, structural truncation, damaged
compressed packets, missing decode, dimensions, color/alpha/intermediate gray,
out-of-range or duplicate/reversed indices, non-exact timing, forged Video and
manifest/PNG provenance, repeated occurrences and absent component selection.
Tests never encode videos dynamically. CI reuses the existing quality matrix
and runs the focused ingestion contract as a mandatory step plus the full suite.

No automatic association/tracking, natural video, VFR, scene cuts, long videos,
streaming, optical flow, UI, Camera replacement or recovery-core refactor is part
of S11D. Pause for review/demo packaging after the matrix passes.
