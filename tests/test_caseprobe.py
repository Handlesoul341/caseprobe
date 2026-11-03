import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "caseprobe" / "scripts" / "caseprobe.py"
EXAMPLE = ROOT / "examples" / "refund"
spec = importlib.util.spec_from_file_location("caseprobe", SCRIPT)
caseprobe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(caseprobe)


def cli(*args, env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], text=True, encoding="utf-8", capture_output=True, env=env)


class CheckTests(unittest.TestCase):
    def test_json_checks_distinguish_missing_null_and_boolean(self):
        checks = [
            {"type": "json_valid"},
            {"type": "json_pointer_equals", "pointer": "/items/0/a~1b", "value": None},
            {"type": "json_pointer_exists", "pointer": "/missing"},
            {"type": "json_pointer_equals", "pointer": "/flag", "value": 1},
        ]
        outcome = caseprobe.check_response('{"items":[{"a/b":null}],"flag":true}', checks)
        self.assertEqual([x["pass"] for x in outcome], [True, True, False, False])

    def test_strict_json_and_text_checks(self):
        self.assertFalse(caseprobe.check_response('{"x": NaN}', [{"type": "json_valid"}])[0]["pass"])
        self.assertFalse(caseprobe.check_response('```json\n{}\n```', [{"type": "json_valid"}])[0]["pass"])
        checks = [{"type": "contains", "value": "你好"}, {"type": "not_contains", "value": "secret"}, {"type": "regex", "value": r"[0-9]+"}, {"type": "max_chars", "value": 5}]
        self.assertTrue(all(x["pass"] for x in caseprobe.check_response("你好123", checks)))

    def test_json_type_check_distinguishes_booleans_and_null(self):
        checks = [
            {"type": "json_pointer_type", "pointer": "/flag", "value": "number"},
            {"type": "json_pointer_type", "pointer": "/flag", "value": "boolean"},
            {"type": "json_pointer_type", "pointer": "/value", "value": "null"},
        ]
        result = caseprobe.check_response('{"flag": true, "value": null}', checks)
        self.assertEqual([check["pass"] for check in result], [False, True, True])

    def test_reject_remote_plain_http_and_credentials_in_url(self):
        for value in ("http://example.com/v1", "https://user:password@example.com/v1", "https://example.com/v1?key=x"):
            with self.subTest(value=value), self.assertRaises(caseprobe.UserError):
                caseprobe.api_endpoint(value)
        self.assertEqual(caseprobe.api_endpoint("http://127.0.0.1:1234/v1"), "http://127.0.0.1:1234/v1/chat/completions")


class OfflineCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_mock(self, fixture, output, cases=None):
        return cli("run", "--cases", cases or EXAMPLE / "cases.jsonl", "--prompt", EXAMPLE / "system-prompt.txt", "--backend", "mock", "--mock-responses", fixture, "--out", output)

    def test_end_to_end_regression_and_private_by_default(self):
        baseline, candidate, comparison = (self.path / name for name in ("baseline.json", "candidate.json", "comparison.md"))
        old = self.run_mock(EXAMPLE / "mock-baseline.json", baseline)
        new = self.run_mock(EXAMPLE / "mock-candidate.json", candidate)
        diff = cli("compare", "--baseline", baseline, "--candidate", candidate, "--out", comparison)
        self.assertEqual((old.returncode, new.returncode, diff.returncode), (0, 1, 1), (old.stderr, new.stderr, diff.stderr))
        self.assertIn("| Regressions | 1 |", comparison.read_text(encoding="utf-8"))
        self.assertIn("prompt_injection", comparison.read_text(encoding="utf-8"))
        report = json.loads(candidate.read_text(encoding="utf-8"))
        self.assertTrue(all("output" not in result for result in report["results"]))
        self.assertEqual(report["results"][-1]["status"], "fail")

    def test_changed_case_and_missing_mock_are_incomparable(self):
        baseline, candidate = self.path / "baseline.json", self.path / "candidate.json"
        self.assertEqual(self.run_mock(EXAMPLE / "mock-baseline.json", baseline).returncode, 0)
        cases = [json.loads(line) for line in (EXAMPLE / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
        cases[0]["input"] += " changed"
        altered = self.path / "changed.jsonl"
        altered.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases), encoding="utf-8")
        self.assertEqual(self.run_mock(EXAMPLE / "mock-baseline.json", candidate, altered).returncode, 0)
        diff = cli("compare", "--baseline", baseline, "--candidate", candidate)
        self.assertEqual(diff.returncode, 2)
        self.assertIn("case definition changed", diff.stdout)
        self.assertIn("| Regressions | 0 |", diff.stdout)
        fixture = self.path / "missing.json"
        fixture.write_text('{}', encoding="utf-8")
        self.assertEqual(self.run_mock(fixture, candidate).returncode, 2)
        diff = cli("compare", "--baseline", baseline, "--candidate", candidate)
        self.assertEqual(diff.returncode, 2)
        self.assertIn("provider or fixture error", diff.stdout)

    def test_different_prompts_can_be_compared_with_the_same_cases(self):
        baseline, candidate = self.path / "baseline.json", self.path / "candidate.json"
        shared = ["--cases", EXAMPLE / "cases.jsonl", "--backend", "mock", "--mock-responses", EXAMPLE / "mock-baseline.json"]
        old = cli("run", *shared, "--prompt", EXAMPLE / "system-prompt-weak.txt", "--out", baseline)
        new = cli("run", *shared, "--prompt", EXAMPLE / "system-prompt.txt", "--out", candidate)
        self.assertEqual((old.returncode, new.returncode), (0, 0))
        old_data = json.loads(baseline.read_text(encoding="utf-8"))
        new_data = json.loads(candidate.read_text(encoding="utf-8"))
        self.assertNotEqual(old_data["prompt_hash"], new_data["prompt_hash"])
        self.assertEqual(cli("compare", "--baseline", baseline, "--candidate", candidate).returncode, 0)

    def test_output_cannot_overwrite_an_input(self):
        original = EXAMPLE / "system-prompt.txt"
        result = cli("run", "--cases", EXAMPLE / "cases.jsonl", "--prompt", original, "--backend", "mock", "--mock-responses", EXAMPLE / "mock-baseline.json", "--out", original)
        self.assertEqual(result.returncode, 2)
        self.assertIn("must differ", result.stderr)

    def test_invalid_case_fails_before_creating_a_report(self):
        broken = self.path / "broken.jsonl"
        broken.write_text('{"id":"duplicate","input":"x","checks":[{"type":"json_valid"}]}\n' * 2, encoding="utf-8")
        output = self.path / "never-created.json"
        result = self.run_mock(EXAMPLE / "mock-baseline.json", output, broken)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Duplicate case id", result.stderr)
        self.assertFalse(output.exists())


class Handler(BaseHTTPRequestHandler):
    requests = []
    response_code = 200
    finish_reason = "stop"

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        type(self).requests.append((self.path, self.headers.get("Authorization"), json.loads(body)))
        self.send_response(type(self).response_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if type(self).response_code == 200:
            self.wfile.write(json.dumps({"choices": [{"finish_reason": type(self).finish_reason, "message": {"content": '{"decision":"eligible"}'}}], "usage": {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}}).encode())
        else:
            self.wfile.write(b'{"error": "should-not-be-saved"}')

    def log_message(self, *args):
        pass


class APICLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        Handler.requests = []
        Handler.response_code = 200
        Handler.finish_reason = "stop"
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.cases = self.path / "cases.jsonl"
        self.cases.write_text(json.dumps({"id": "one", "input": "你好", "checks": [{"type": "json_pointer_equals", "pointer": "/decision", "value": "eligible"}]}, ensure_ascii=False) + "\n", encoding="utf-8")
        self.prompt = self.path / "prompt.txt"
        self.prompt.write_text("system instruction", encoding="utf-8")
        self.report = self.path / "run.json"
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def tearDown(self):
        self.temp.cleanup()

    def run_api(self, *extra):
        env = dict(os.environ, CASEPROBE_TEST_KEY="private-test-key")
        return cli("run", "--cases", self.cases, "--prompt", self.prompt, "--backend", "api", "--base-url", self.base_url, "--model", "test-model", "--api-key-env", "CASEPROBE_TEST_KEY", "--out", self.report, *extra, env=env)

    def test_chat_request_response_and_usage(self):
        result = self.run_api("--include-output")
        self.assertEqual(result.returncode, 0, result.stderr)
        path, auth, body = Handler.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(auth, "Bearer private-test-key")
        self.assertEqual(body["messages"][1], {"role": "user", "content": "你好"})
        self.assertNotIn("temperature", body)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["results"][0]["usage"]["total_tokens"], 8)
        self.assertEqual(report["results"][0]["output"], '{"decision":"eligible"}')
        self.assertNotIn("private-test-key", self.report.read_text(encoding="utf-8"))

    def test_http_error_is_not_a_case_failure_and_body_is_not_saved(self):
        Handler.response_code = 429
        result = self.run_api()
        self.assertEqual(result.returncode, 2)
        report = self.report.read_text(encoding="utf-8")
        self.assertEqual(json.loads(report)["results"][0]["status"], "error")
        self.assertNotIn("should-not-be-saved", report)
        self.assertIn("HTTP 429", report)

    def test_truncated_completion_is_incomparable_even_if_its_text_passes(self):
        Handler.finish_reason = "length"
        result = self.run_api()
        self.assertEqual(result.returncode, 2)
        item = json.loads(self.report.read_text(encoding="utf-8"))["results"][0]
        self.assertEqual(item["status"], "error")
        self.assertIn("truncated", item["error"])

    def test_local_endpoint_can_run_without_auth_and_passes_optional_temperature(self):
        result = self.run_api("--no-auth", "--temperature", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        _, auth, body = Handler.requests[0]
        self.assertIsNone(auth)
        self.assertEqual(body["temperature"], 0)


if __name__ == "__main__":
    unittest.main()
