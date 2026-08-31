from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .editor_motion import MotionEditorSession

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENT = REPOSITORY_ROOT / "examples" / "017-motion-rectangle.svm.json"
STATIC_ROOT = REPOSITORY_ROOT / "editor" / "motion-timeline"
MAX_REQUEST_BYTES = 16_384


class MotionEditorHandler(SimpleHTTPRequestHandler):
    session: MotionEditorSession
    session_lock = threading.Lock()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._handle(lambda: self.session.state(_tick(parsed.query)))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        actions = {
            "/api/preview": lambda payload: self.session.preview(payload["value"], payload["tick"]),
            "/api/commit": lambda payload: self.session.commit(payload["value"], payload["tick"]),
            "/api/checkout-parent": lambda payload: self.session.checkout_parent(payload["tick"]),
            "/api/clear-preview": lambda payload: self._clear_preview(payload["tick"]),
        }
        action = actions.get(parsed.path)
        if action is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_payload()
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._handle(lambda: action(payload))

    def _clear_preview(self, tick: int) -> dict[str, Any]:
        self.session.clear_preview()
        return self.session.state(tick)

    def _handle(self, action: Any) -> None:
        try:
            with self.session_lock:
                result = action()
        except (KeyError, TypeError, ValueError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._json(result)

    def _read_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= MAX_REQUEST_BYTES:
            raise ValueError("Editor request body size is invalid")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("Editor request must be a JSON object")
        return payload

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _tick(query: str) -> int:
    values = parse_qs(query).get("tick", ["0"])
    return int(values[0])


def create_server(
    document_path: Path = DEFAULT_DOCUMENT,
    *,
    host: str = "127.0.0.1",
    port: int = 4175,
) -> ThreadingHTTPServer:
    document = json.loads(document_path.read_text(encoding="utf-8"))
    MotionEditorHandler.session = MotionEditorSession(document)
    return ThreadingHTTPServer((host, port), MotionEditorHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Editor Vertical Slice 01")
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4175)
    args = parser.parse_args()
    server = create_server(args.document, host=args.host, port=args.port)
    print(f"SVM Motion Editor listening on http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
