# Bounded authored raster production Golden

See [spec/75](../../spec/75-authored-multipart-raster-production.md).
`source.svg` independently records one explicit assembly and its complete two
triangular path parts. The geometry was chosen analytically from frozen P2A
conditions before raster measurement. No video-derived source or sidecar exists.

`scene.avi` contains exactly two 256×256 FFV1 grayscale frames at 1 FPS. The second
translates both source parts by (8,6). It was encoded offline using the existing
pinned OpenCV/FFmpeg backend:

```powershell
python -m tools.build_authored_raster_fixture
```

The helper immediately verifies exact spec/59 decode against independently
reproduced frames. Re-encoding byte identity is not promised or required; tests
consume the immutable checked-in AVI and never re-encode it. A different AVI
requires new recorded video/occurrence/dependent Golden identities even if its
canonical pixels are identical. Do not overwrite Golden identities to conceal
an unexplained mismatch.

Measured SHA-256 identities:

| Artifact | SHA-256 |
| --- | --- |
| Source | `230e61f5624f9f191b510b7e16ec826e585b7333a0848b3823768ffe07310268` |
| AVI | `9bfd843fc6d4ca565afecd0565965b0aa73012d963e059e3caf93a65cdbf368e` |
| Frame 0 | `004da87d3c79252721c758ee4d366cb46618c8c6392481a58c15f9c1a75f99d6` |
| Frame 1 | `4e5e1025dcc8035eb1108b9844854f1f1b9b29b25cd792508471e9694420c0b5` |
| Production report | `3df09bea2ea60d63b819cf0270da6b11db45915782c59070a2f631c1897c3f3d` |

`golden.json` records the complete diagnostic report, including four mask IDs,
accepted source/video/manifest/P2A/P2B descriptors, revision identities, source
subject/part identities, exact observation mappings and all measurements. Tests
reproduce it from the real source and AVI through accepted unchanged P2A/P2B.
Expected hashes are regression checks, not verification authority.

The test host accepts immutable input references using the existing trusted
Revision Store fixture mechanism. Production code never commits a transaction;
its report is not accepted spec/74 evidence. No artwork, Group, construction
receipt, TemporalIdentity or binding is created by this Golden.
