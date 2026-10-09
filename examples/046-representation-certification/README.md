# Present-time representation certification Golden

This fixture reuses the exact authored two-triangle source/video from example
043, genuine Spec76/77 ownership admission, the accepted whole-subject identity
from example 045, and the source-fixed Group construction from Spec78. It does
not create or modify geometry, Group members, TemporalIdentity bindings, motion
bindings or animation.

`certification.json` is the complete canonical certification artifact;
`accepted.svm.json` records the exact accepted portable Document, and
`golden.json` pins its measured identities and acceptance event. Consuming the
association authority requires authenticated host history and its admission
event in addition to this Document and its reference. The mode is
`PRESENT_TIME_CERTIFICATION@0.1`. Birth replay proves
`STRUCTURAL_CONFORMITY_ONLY`: the authenticated pre/post states match the legal
F0 construction recipe. It does not claim that a historical dedicated F0 verifier
ran. Both indistinguishable trusted low-level and dedicated F0 births can be
independently certified now through the new exclusive acceptance boundary.

The genuine source-backed whole TemporalIdentity and Group retain their frozen
identities. The birth manifest/receipt hashes record this fixture's construction
base, which already contains the example 045 whole identity. The existing F0
receipt remains unchanged with `representation_claim: null`. Certification
appends one reference and emits one current trusted admission event atomically.

Rendering remains byte-identical to `../044-video-artwork-construction/group.svg`.
The certification profile deliberately admits only the unchanged birth
representation and two-occurrence identity projection. Ordinary edits remain
legal, but relevant geometry/style/transform/Track changes invalidate this
version's current proof. Later consumers must authenticate the event and
independently replay coverage, construction history and current applicability;
canonical bytes or Artifact presence alone confer no association authority.

Reproduce acceptance, the adversarial matrix and the trusted-history roundtrip
from the repository root:

```powershell
python -m unittest discover -s tests -p test_representation_certification.py -v
```
