# Golden 047 — real fogleman/primitive toolchain run

This directory is the frozen evidence for the first real external-tool chain:

```text
source.png
-> fogleman/primitive
-> primitive.svg + primitive.png
-> restricted normalization
-> normalized.svg
-> SVGImportAdapter / ProposalAcceptor
-> accepted.svm.json + Revision identity
-> FINAL SVGRenderer
-> svm.svg
```

`source.png` is an exact copy of the checked-in real Golden P raster at
`examples/derived/020-pop-output/real/upstream.png`, not a generated unit-test
stub. Its content identity is
`sha256:f0fe6d0588977fcc955cc0e9eaca51f7d022dca327373afa8c78325f3aeec753`.

## Actual run

The executable was built from:

- `fogleman/primitive` commit
  `0373c216458be1c4b40655b796a3aefedf8b7d23`;
- Go `1.27.2 windows/amd64`;
- `fogleman/gg` `a9ff18eccd6d57b3c8576a71a91a04868f62078c`;
- `golang/freetype` `e2365dfdc4a05e4b8299a783240d4a7d5a65d4e4`;
- `nfnt/resize` `83c6a9932646f83e3267f353373d47347b6036b2`;
- `golang/image` `f315e440302883054d0c2bd85486878cb4f8572c`.

The built executable SHA-256 was
`f3f627ca5dd924f91b22421dea660fc0d287bba0b35e6dde894abca2aa0ae2d2`.
It was invoked through the checked-in CLI behavior with:

```powershell
python -m svm import-primitive examples/005-empty-canvas.svm.json `
  examples/derived/020-pop-output/real/upstream.png `
  --primitive-executable C:\path\to\primitive.exe `
  --engine-commit 0373c216458be1c4b40655b796a3aefedf8b7d23 `
  --output-directory examples/047-fogleman-primitive-toolchain `
  --namespace primitive-real `
  --shapes 12 --mode combo --alpha 128 `
  --input-size 128 --output-size 256 --workers 1
```

The fit took `1.937586s` on the producing machine; the entire in-process chain
took `1.962181s`. Performance is evidence, not a normative budget.

The run produced 12 fitted shapes plus one explicit background. Acceptance
created Proposal `proposal:svg-import:6f23f3826e326202` and Revision
`revision:b421afd62c1fd52d7d95e0fd0a0ee69404dfa70cc2829e24aa2eac589d645f02`.

## Replay

Replay does not require the executable:

```powershell
python -m svm replay-primitive examples/005-empty-canvas.svm.json `
  examples/047-fogleman-primitive-toolchain
```

It reproduces the same Proposal and Revision, accepted Document SHA-256
`831bd673b799cdf667f4e45926908a0989de5e75e943aaff684da44d9f936b82`,
and deterministic SVG SHA-256
`deb59eeaa1ad80746087860fb83fba69cd5959b419fcb94d9aa68f211e2a7f59`.

`svm.png` is supplementary visual QA, rasterized from `svm.svg` with Microsoft
Edge `154.0.4258.62`; it is intentionally outside the CLI bundle manifest.
Compared with Primitive's native `primitive.png`, mean absolute RGBA channel
errors are `[0.266144, 0.336258, 0.124069, 0]` on the 0–255 scale, with maxima
`[74, 77, 42, 0]`. The low aggregate difference permits anti-aliasing edge
differences while checking geometry, draw order, color, alpha, and canvas.

## Files

- `source.png` — frozen real PNG input;
- `primitive.svg` — exact native vector output and deterministic replay boundary;
- `primitive.png` — exact native raster preview;
- `normalized.svg` — strict Core-compatible SVG;
- `accepted.svm.json` — accepted editable Document;
- `svm.svg` — deterministic FINAL SVM render;
- `svm.png` — supplementary rasterized visual comparison;
- `run-manifest.json` — canonical hashes, provenance, parameters, performance,
  Proposal, Transaction, Revision, and replay expectations.

The upstream execution itself is not reproducible because the tool seeds global
and per-worker RNGs from the clock and exposes no seed flag. This directory
freezes the concrete output; it does not conceal that production blocker.
