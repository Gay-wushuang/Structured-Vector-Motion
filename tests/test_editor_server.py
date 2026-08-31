import http.client
import json
import threading
import unittest

from svm.editor_server import create_server


class EditorServerTrustBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = create_server(port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(
        self,
        *,
        content_type: str = "application/json",
        origin: str | None = None,
        authority: str | None = "1",
        host: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=2)
        headers = {"Content-Type": content_type}
        if origin is not None:
            headers["Origin"] = origin
        if authority is not None:
            headers["X-SVM-Editor-Request"] = authority
        if host is not None:
            headers["Host"] = host
        payload = json.dumps(
            {
                "track_id": "track:moving-rectangle-x",
                "keyframe_id": "keyframe:moving-x-0500",
                "value": 350,
                "tick": 500,
            }
        )
        connection.request("POST", "/api/preview", body=payload, headers=headers)
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response.status, body

    def test_same_origin_json_request_with_editor_header_is_accepted(self) -> None:
        status, payload = self.request(origin=f"http://{self.host}:{self.port}")
        self.assertEqual(status, 200)
        self.assertTrue(payload["preview"]["active"])

    def test_non_browser_request_may_omit_origin_but_not_editor_header(self) -> None:
        status, payload = self.request()
        self.assertEqual(status, 200)
        self.assertTrue(payload["preview"]["active"])

    def test_missing_editor_authority_header_is_rejected(self) -> None:
        status, payload = self.request(authority=None)
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Missing Editor request authority")

    def test_cross_origin_request_is_rejected(self) -> None:
        status, payload = self.request(origin="https://attacker.invalid")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Untrusted Editor Origin")

    def test_non_json_request_is_rejected(self) -> None:
        status, payload = self.request(content_type="text/plain")
        self.assertEqual(status, 415)
        self.assertEqual(payload["error"], "Editor mutations require application/json")

    def test_untrusted_host_is_rejected(self) -> None:
        status, payload = self.request(host="attacker.invalid")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "Untrusted Editor Host")


if __name__ == "__main__":
    unittest.main()
