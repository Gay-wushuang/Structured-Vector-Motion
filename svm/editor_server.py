from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from .editor_motion import DocumentEditorSession

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENT = REPOSITORY_ROOT / "examples" / "017-motion-rectangle.svm.json"
STATIC_ROOT = REPOSITORY_ROOT / "editor" / "motion-timeline"
MAX_REQUEST_BYTES = 16_384
EDITOR_REQUEST_HEADER = "X-SVM-Editor-Request"
EDITOR_REQUEST_VALUE = "1"


class MotionEditorHandler(SimpleHTTPRequestHandler):
    session: DocumentEditorSession
    session_lock = threading.Lock()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if not self._trusted_host():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._handle(lambda: self.session.state(_tick(parsed.query)))
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self._trusted_host():
            return
        parsed = urlparse(self.path)
        actions = {
            "/api/preview": lambda payload: self.session.preview(
                payload["track_id"], payload["keyframe_id"], payload["value"], payload["tick"]
            ),
            "/api/commit": lambda payload: self.session.commit(
                payload["track_id"], payload["keyframe_id"], payload["value"], payload["tick"]
            ),
            "/api/checkout-parent": lambda payload: self.session.checkout_parent(payload["tick"]),
            "/api/clear-preview": lambda payload: self._clear_preview(payload["tick"]),
        }
        action = actions.get(parsed.path)
        if action is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not self._trusted_mutation_request():
            return
        try:
            payload = self._read_payload()
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._handle(lambda: action(payload))

    def _trusted_mutation_request(self) -> bool:
        host, port = cast(tuple[str, int], self.server.server_address)
        expected_origin = f"http://{host}:{port}"
        origin = self.headers.get("Origin")
        if origin is not None and origin != expected_origin:
            self._json({"error": "Untrusted Editor Origin"}, HTTPStatus.FORBIDDEN)
            return False
        if self.headers.get_content_type() != "application/json":
            self._json(
                {"error": "Editor mutations require application/json"},
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
            return False
        if self.headers.get(EDITOR_REQUEST_HEADER) != EDITOR_REQUEST_VALUE:
            self._json({"error": "Missing Editor request authority"}, HTTPStatus.FORBIDDEN)
            return False
        return True

    def _trusted_host(self) -> bool:
        host, port = cast(tuple[str, int], self.server.server_address)
        if self.headers.get("Host") == f"{host}:{port}":
            return True
        self._json({"error": "Untrusted Editor Host"}, HTTPStatus.FORBIDDEN)
        return False

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

    class SessionEditorHandler(MotionEditorHandler):
        session = DocumentEditorSession(document)
        session_lock = threading.Lock()

    return ThreadingHTTPServer((host, port), SessionEditorHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Editor Vertical Slice 02")
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
