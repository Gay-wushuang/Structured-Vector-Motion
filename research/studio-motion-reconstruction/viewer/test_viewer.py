from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ..fixture import make
from ..run import json_bytes, observe, read_settings
from .__main__ import build_html, load_view


class CandidateViewerTest(unittest.TestCase):
    def test_matching_frames_only_and_original_clock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "preview-input"
            make(bundle)
            source = bundle / "synthetic.avi"
            candidate_path = bundle / "candidate.json"
            candidate = observe(source.read_bytes(), read_settings(bundle / "seeds.json"))
            candidate_path.write_bytes(json_bytes(candidate))

            preview = load_view(source, candidate_path, synthetic=True)
            self.assertTrue(preview["synthetic"])
            self.assertEqual(len(preview["sourcePngBase64"]), len(candidate["frames"]))
            self.assertTrue(preview["sourcePngBase64"][0].startswith("iVBORw0KGgo"))
            document = build_html(preview)
            self.assertIn("Content-Security-Policy", document)
            payload = document.split('id="data">', 1)[1].split("</script>", 1)[0]
            decoded = json.loads(payload)
            self.assertEqual(decoded["candidate"]["frames"], candidate["frames"])
            self.assertTrue(decoded["candidate"]["unknown_tick_intervals_inclusive"]["amber"])

            candidate["frames"][0]["tick"] += 1
            candidate_path.write_bytes(json_bytes(candidate))
            with self.assertRaisesRegex(ValueError, "clock differs"):
                load_view(source, candidate_path)

            candidate["frames"][0]["bgr24_sha256"] = "0" * 64
            candidate_path.write_bytes(json_bytes(candidate))
            with self.assertRaisesRegex(ValueError, "Decoded batch differs"):
                load_view(source, candidate_path)


if __name__ == "__main__":
    unittest.main()
