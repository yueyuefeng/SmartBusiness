import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from smartbusiness.service import BusinessService
from smartbusiness.server import make_server


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = BusinessService(Path(self.tmp.name) / "test.sqlite3")
        self.token = "test-only-agent-token-not-for-deployment"
        self.server = make_server(self.service, self.token)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_api_requires_credentials(self):
        self.assertEqual(self.request("GET", "/api/dashboard")[0], 401)
        status, headers, body = self.request("GET", "/api/dashboard", headers={"Authorization": "Bearer " + self.token})
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["cases"]), 6)
        self.assertNotIn(self.token.encode(), body)

    def test_foreign_host_and_origin_rejected(self):
        for headers in ({"Host": "attacker.example"}, {"Origin": "https://attacker.example"}):
            status, _, _ = self.request("GET", "/api/dashboard", headers=headers | {"Authorization": "Bearer " + self.token})
            self.assertEqual(status, 403)

    def test_browser_cookie_and_content_security_policy(self):
        status, headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.request("GET", "/api/dashboard", headers={"Cookie": cookie})[0], 200)

    def test_browser_mutation_requires_same_origin(self):
        cookie = self.request("GET", "/")[1]["Set-Cookie"].split(";", 1)[0]
        payload = json.dumps({"operation": "add_contact", "payload": {"name": "Alice", "company": "demo", "channel": "mail", "external_ref": "local"}, "idempotency_key": "api-1"})
        headers = {"Cookie": cookie, "Content-Type": "application/json"}
        self.assertEqual(self.request("POST", "/api/commands", payload, headers)[0], 403)
        self.assertEqual(self.request("POST", "/api/commands", payload, headers | {"Origin": self.origin})[0], 200)

    def test_agent_role_cannot_be_overridden_by_payload(self):
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        payload = json.dumps({"operation": "review_content", "payload": {}, "idempotency_key": "api-2"})
        self.assertEqual(self.request("POST", "/api/commands", payload, headers)[0], 403)
        payload = json.dumps({"operation": "add_contact", "payload": {}, "idempotency_key": "api-2", "actor": "operator"})
        self.assertEqual(self.request("POST", "/api/commands", payload, headers)[0], 400)

    def test_malformed_and_oversized_body_rejected(self):
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        for body in ("{", "[]", '{"operation":NaN}', '{"operation":"x","operation":"y"}'):
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/api/commands", body, headers)[0], 400)
        self.assertEqual(self.request("POST", "/api/commands", "x" * 131073, headers)[0], 413)

    def test_static_path_traversal_blocked(self):
        for path in ("/../.smartbusiness/api-token", "/%2e%2e/.smartbusiness/api-token", "/server.py", "/.smartbusiness/business.sqlite3"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_agent_case_read_and_finance_simulation_end_to_end(self):
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        self.assertEqual(self.request("GET", "/api/cases/EN-H01", headers=headers)[0], 200)
        payload = json.dumps({"operation": "evaluate_case", "payload": {"case_id": "EN-H01", "revenue": "10000"}, "idempotency_key": "api-sim-1"})
        status, _, body = self.request("POST", "/api/commands", payload, headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["result"]["finance"]["contribution_profit"], "2700")
        replay = self.request("POST", "/api/commands", payload, headers)
        self.assertTrue(json.loads(replay[2])["replayed"])


if __name__ == "__main__":
    unittest.main()
