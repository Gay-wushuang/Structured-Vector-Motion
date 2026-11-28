import base64
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

import cv2
import numpy as np

from svm.phase1_demo import load_config, run_demo
from svm.proposals import ProposalConflictError
from svm.studio import Studio

SVG_NS = {"svg": "http://www.w3.org/2000/svg"}


class StudioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.studio = Studio()

    def action(self, action, **fields):
        return self.studio.action({"action": action, "revision": self.studio.head, **fields})

    def test_shape_animation_history_and_native_round_trip(self) -> None:
        self.action("new")
        shape = self.action("shape", kind="CreateRectangle", name="Box", fill="#aaccbb")
        operation = shape["document"]["construction"]["operations"][0]["id"]
        self.action("parameter", operation=operation, property="width", value=160)
        revised = self.action("keyframe", operation=operation, property="width", value=200, tick=24)

        def width(state):
            node = ElementTree.fromstring(state["svg"]).find(".//svg:rect", SVG_NS)
            assert node is not None
            return float(node.attrib["width"])

        self.assertEqual(width(self.studio.state(0)), 160)
        self.assertEqual(width(self.studio.state(12)), 180)
        self.assertEqual(width(revised), 200)
        self.assertEqual(width(self.action("undo", tick=24)), 160)
        self.assertEqual(self.action("redo", tick=24)["revision"], revised["revision"])
        self.assertEqual(self.studio.state(24)["svg"], revised["svg"])
        saved = json.loads(json.dumps(revised["document"]))
        self.assertEqual(self.action("open", document=saved)["document"], saved)
        self.assertEqual(width(self.studio.state(24)), 200)

    def test_svg_import_and_unsupported_svg_rollback(self) -> None:
        initial = self.action("new")
        imported = self.action(
            "import",
            svg=(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                '<path d="M 5 5 L 95 5 L 95 95 Z" fill="#aaccbb"/></svg>'
            ),
        )
        self.assertNotEqual(imported["revision"], initial["revision"])
        self.assertIn("<path", imported["svg"])
        with self.assertRaises(ValueError):
            self.action("import", svg='<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>')
        self.assertEqual(self.studio.state(0), imported)
        self.assertEqual(self.action("undo")["revision"], initial["revision"])

    def test_invalid_and_stale_mutations_leave_revision_intact(self) -> None:
        baseline = self.studio.state(0)
        with self.assertRaises(ValueError):
            self.action("parameter", operation="op:satellite", property="rx", value=-1)
        with self.assertRaises(ProposalConflictError):
            self.studio.action({"revision": "revision:stale", "action": "new"})
        self.assertEqual(self.studio.state(0), baseline)

    def test_canvas_move_is_one_revision_at_the_playhead(self) -> None:
        initial = self.studio.state(0)
        moved = self.action("move", operation="op:satellite", x=510, y=350, tick=48)
        tracks = moved["document"]["animation"]["content"]
        updated = {
            track["target"]["parameter"]: next(
                frame["value"] for frame in track["keyframes"] if frame["tick"] == 48
            )
            for track in tracks
        }
        self.assertEqual(updated, {"cx": 510, "cy": 350})
        self.assertEqual(self.action("undo")["revision"], initial["revision"])


class StudioRecoveryTest(unittest.TestCase):
    def test_guided_source_from_lossless_avi(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clip = Path(temp) / "guided.avi"
            writer = cv2.VideoWriter(
                str(clip), cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*"FFV1"), 12, (80, 64)
            )
            try:
                self.assertTrue(writer.isOpened(), "The guided fixture requires FFV1 encoding")
                for x, y in ((30, 30), (38, 36)):
                    frame = np.zeros((64, 80, 3), dtype=np.uint8)
                    frame[y : y + 12, x : x + 12] = (42, 181, 247)
                    writer.write(frame)
            finally:
                writer.release()
            source = clip.read_bytes()

        studio = Studio()
        revision = studio.head

        def action(name, **fields):
            return studio.action({"action": name, "revision": revision, **fields})

        info = action("inspect-guided-source", source=base64.b64encode(source).decode())
        self.assertEqual(info["frameCount"], 2)
        self.assertTrue(info["image"].startswith("data:image/png;base64,"))
        analyzed = action("analyze-guided-source", x=35, y=35)
        self.assertEqual(len(analyzed["observedTicks"]), 2)
        tick0, tick1 = analyzed["observedTicks"]
        prepared = action("prepare-guided-segment", start=tick0, end=tick1)["segment"]
        self.assertEqual(studio.head, revision)
        accepted = action("accept-segment", preview=prepared["id"])
        self.assertEqual(accepted["authoredEndTick"], tick1 - tick0)
        ns = "{http://www.w3.org/2000/svg}"
        first = ElementTree.fromstring(prepared["firstSvg"]).find(f".//{ns}rect")
        last = ElementTree.fromstring(studio.state(tick1 - tick0)["svg"]).find(f".//{ns}rect")
        assert first is not None and last is not None
        self.assertEqual(int(last.attrib["x"]) - int(first.attrib["x"]), 8)
        self.assertEqual(int(last.attrib["y"]) - int(first.attrib["y"]), 6)

    def test_generated_segment_preview_and_acceptance(self) -> None:
        studio = Studio()
        before = studio.state(0)
        state = studio.action({"action": "prepare-demo-segment", "revision": studio.head})
        preview = state["segment"]
        self.assertTrue(preview["synthetic"])
        self.assertNotEqual(preview["firstSvg"], preview["lastSvg"])
        self.assertEqual(studio.state(0), before)
        with self.assertRaises(ProposalConflictError):
            studio.action({"action": "accept-segment", "revision": studio.head, "preview": "wrong"})
        accepted = studio.action(
            {
                "action": "accept-segment",
                "revision": studio.head,
                "preview": preview["id"],
            }
        )
        self.assertEqual(accepted["authoredEndTick"], 94)
        self.assertEqual(accepted["segmentReceipt"]["track_count"], 2)
        self.assertEqual(len(accepted["document"]["references"]), 1)
        self.assertEqual(studio.state(94)["svg"], preview["lastSvg"])
        undone = studio.action({"action": "undo", "revision": studio.head})
        self.assertEqual(undone["document"]["entities"], [])
        self.assertFalse(undone["undo"])

    def test_controlled_video_edit_undo_reopen_and_failed_import(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / "phase1"
            run_demo(root, load_config(root), bundle)
            studio = Studio(bundle)

            def action(name, **fields):
                return studio.action({"action": name, "revision": studio.head, **fields})

            baseline = action("recovery")
            self.assertEqual(baseline["source"]["ticks"], (0, 12, 24, 36))
            self.assertEqual(studio.state(11)["source"]["tick"], 0)
            exact = studio.state(12)
            self.assertEqual(exact["source"]["tick"], 12)
            self.assertNotEqual(baseline["source"]["url"], exact["source"]["url"])
            document = baseline["document"]
            tracks = document["animation"]["content"]
            track = next(item for item in tracks if item["target"].get("property") == "translate.x")
            with self.assertRaisesRegex(ValueError, "已有关键帧"):
                action("preview-keyframe", track=track["id"], tick=11, value=17)
            with self.assertRaisesRegex(ValueError, "请先预览"):
                action("track-keyframe", track=track["id"], tick=12, value=17)
            self.assertEqual(studio.head, baseline["revision"])

            preview = action("preview-keyframe", track=track["id"], tick=12, value=17)
            self.assertEqual(preview["revision"], baseline["revision"])
            self.assertEqual(preview["document"], document)
            self.assertEqual(preview["svg"], exact["svg"])
            self.assertNotEqual(preview["preview"]["svg"], exact["svg"])
            self.assertEqual(studio.state(24)["preview"]["svg"], studio.state(24)["svg"])
            self.assertIsNone(action("clear-preview", tick=12)["preview"])
            action("preview-keyframe", track=track["id"], tick=12, value=17)
            with self.assertRaises(ProposalConflictError):
                action("accept-preview", tick=12, preview="proposal:stale")
            self.assertEqual(studio.head, baseline["revision"])
            edited = action("accept-preview", tick=12, preview=preview["preview"]["id"])
            other_tracks = [item for item in tracks if item["id"] != track["id"]]
            self.assertEqual(edited["motionValues"][track["id"]], 17)
            self.assertEqual(exact["source"], edited["source"])
            self.assertIsNone(edited["preview"])
            self.assertEqual(preview["preview"]["svg"], edited["svg"])
            self.assertNotEqual(exact["svg"], edited["svg"])
            self.assertEqual(
                [
                    item
                    for item in edited["document"]["animation"]["content"]
                    if item["id"] != track["id"]
                ],
                other_tracks,
            )
            self.assertEqual(action("undo", tick=12)["svg"], exact["svg"])
            self.assertEqual(action("redo", tick=12)["svg"], edited["svg"])
            saved = json.loads(json.dumps(edited["document"]))
            self.assertEqual(action("open", document=saved)["source"]["tick"], 0)
            self.assertEqual(studio.state(12)["svg"], edited["svg"])

            altered = deepcopy(saved)
            altered["groups"][0]["members"].pop()
            with self.assertRaises(ValueError):
                action("open", document=altered)
            self.assertEqual(studio.state(12)["svg"], edited["svg"])

            document_path = bundle / "documents/recovered.svm.json"
            document_path.write_text(json.dumps(altered), encoding="utf-8")
            tampered = Studio(bundle)
            with self.assertRaisesRegex(ValueError, "登记的快照"):
                tampered.action({"action": "recovery", "revision": tampered.head})


if __name__ == "__main__":
    unittest.main()
