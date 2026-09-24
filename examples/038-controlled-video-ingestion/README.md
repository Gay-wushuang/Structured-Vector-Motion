# Controlled Video -> Editable SVM v0 fixture

These small AVI/FFV1 files were encoded offline using the repository's pinned
OpenCV 4.14.0 / opencv-python-headless 4.14.0.94 wheel, explicit CAP_FFMPEG,
VideoWriter_fourcc("FFV1"), grayscale input and 1200 x 900 dimensions. No external
ffmpeg executable was used. Tests never generate or re-encode video.

| File | Source S11C PNG ticks | Actual AVI FPS | Bytes |
| --- | --- | --- | ---: |
| scene.avi | 0,12,24,36 | 1/1 | 15008 |
| repeated.avi | 0,0 | 1/1 | 10326 |
| fractional.avi | 0,12 | 2997/100 | 11058 |

Source PNGs, registered Recovery Document and explicit selectors are frozen in
`examples/037-explicit-multi-object-raster-recovery`. Scene content is two static
asymmetric anchors, two independently moving asymmetric targets and one shared
pan/rotation/zoom Camera, with Camera hold between recovered ticks 12 and 24.

The fractional fixture intentionally exposes writer behavior: requesting
30000/1001 FPS produced AVI header rate/scale 2997/100. Ingestion reads that exact
header; it does not silently reinterpret 29.97 as 30000/1001. At 2997 ticks/second,
indices 0,1 map to ticks 0,100. The scene fixture maps 0,1,2,3 to 0,12,24,36 with
12 ticks/second.

On the Windows development wheel, all decoded frames are exact gray black/white
copies of their reference PNG pixels. Canonical encoding reuses SVM's existing
stored-DEFLATE PNG encoder; raw compressed reference PNG files have different
bytes, while independently canonicalized reference PNGs are byte-identical.

Canonical scene SHA-256 digests, also printed and checked by the CI codec test:

```text
0  b268898b92a773239151f54e53feb503d0d26f189a5a0028fea7c20b747fd4c4
1  8a53674a074cb244fe65d2de945319c8398221889266777c359edb804ba3e09d
2  86f8c75a769182d26ded5904e4a866c8ad8f3c15bfcd65f9b17483f11a5ddea2
3  371b1b80d20d604859d1592bf5755de08655b8f0abe7fe8d2ad91cf3fc37ab2b
```

The digest listing documents measured outputs; tests derive expected bytes from
the independent checked-in reference PNGs rather than hardcoding these IDs.
Repeated video frames retain one PNG Artifact identity and two source/tick
occurrence identities.

`test_video_ingestion.py` is mandatory on the existing Ubuntu/Windows x Python
3.11/3.12 matrix. It prints bundled FFmpeg build versions, verifies the real
decoder and compares canonical bytes. No platform skip or codec fallback exists.
`test_video_recovery.py` forbids reference PNG/Ground Truth reads in the video
branch, then proves 12-Track equivalence and the full input-bundle lineage.

Video recovery maxima match S11C: A position 0.678731 px, rotation 0.085918 deg,
scale 0.003163; B 0.369451 px, 0.081817 deg, 0.001756; Camera 0.624716 px,
0.077882 deg, 0.000977. Maximum presented landmark error is 1.434876 px. Existing
raster policies and limits are unchanged.

The exported input bundle contains source Video, manifest and canonical PNGs.
Retain the manifest alongside the recovered Document: it joins PNG ID/tick to
Video occurrence without injecting video-specific identity into PNG consumers.
See `spec/59-deterministic-video-frame-ingestion.md` for the supported subset,
verification rules, API and CLI.
