#!/usr/bin/env python3
"""CaseProbe: small, dependency-free regression checks for chat models."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib import error, parse, request


VERSION = "0.1.0"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
MISSING = object()


class UserError(Exception):
    pass


def json_loads(text: str):
    def bad_constant(value):
        raise ValueError(f"invalid JSON constant: {value}")
    return json.loads(text, parse_constant=bad_constant)


def read_json(path: Path):
    try:
        return json_loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise UserError(f"Cannot read valid JSON from {path}: {exc}") from exc


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise UserError(f"Cannot read {path}: {exc}") from exc


def digest(value) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def pointer_parts(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise UserError("JSON pointer must be empty or start with '/'")
    parts = []
    for part in pointer.split("/")[1:] if pointer else []:
        if re.search(r"~(?![01])", part):
            raise UserError("Invalid JSON pointer escape; use ~0 or ~1")
        parts.append(part.replace("~1", "/").replace("~0", "~"))
    return parts


def resolve_pointer(value, pointer: str):
    for part in pointer_parts(pointer):
        if isinstance(value, dict):
            if part not in value:
                return MISSING
            value = value[part]
        elif isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", part):
                return MISSING
            index = int(part)
            if index >= len(value):
                return MISSING
            value = value[index]
        else:
            return MISSING
    return value


def json_equal(left, right) -> bool:
    # bool is a subclass of int in Python, but they are distinct JSON types.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(left[k], right[k]) for k in left)
    return left == right


def validate_check(check, case_id: str):
    if not isinstance(check, dict) or not isinstance(check.get("type"), str):
        raise UserError(f"Case {case_id}: every check needs a type")
    kind = check["type"]
    if kind in ("equals", "contains", "not_contains", "regex"):
        if not isinstance(check.get("value"), str):
            raise UserError(f"Case {case_id}: {kind} requires string value")
        if kind == "regex":
            try:
                re.compile(check["value"])
            except re.error as exc:
                raise UserError(f"Case {case_id}: invalid regex: {exc}") from exc
    elif kind in ("json_pointer_exists", "json_pointer_equals", "json_pointer_type"):
        pointer_parts(check.get("pointer"))
        if kind == "json_pointer_equals" and "value" not in check:
            raise UserError(f"Case {case_id}: json_pointer_equals requires value")
        if kind == "json_pointer_type" and check.get("value") not in ("null", "boolean", "number", "string", "array", "object"):
            raise UserError(f"Case {case_id}: json_pointer_type requires a JSON type name")
    elif kind == "json_valid":
        pass
    elif kind == "max_chars":
        if type(check.get("value")) is not int or check["value"] < 0:
            raise UserError(f"Case {case_id}: max_chars requires a nonnegative integer")
    else:
        raise UserError(f"Case {case_id}: unsupported check {kind!r}")


def load_cases(path: Path) -> list[dict]:
    cases, seen = [], set()
    for line_no, line in enumerate(read_text(path).splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json_loads(line)
        except ValueError as exc:
            raise UserError(f"Invalid JSON on line {line_no}: {exc}") from exc
        if not isinstance(case, dict):
            raise UserError(f"Line {line_no}: expected an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not ID_RE.fullmatch(case_id):
            raise UserError(f"Line {line_no}: id must contain only ASCII letters, numbers, . _ -")
        if case_id in seen:
            raise UserError(f"Duplicate case id: {case_id}")
        if not isinstance(case.get("input"), str):
            raise UserError(f"Case {case_id}: input must be a string")
        checks = case.get("checks")
        if not isinstance(checks, list) or not checks:
            raise UserError(f"Case {case_id}: provide at least one check")
        tags = case.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise UserError(f"Case {case_id}: tags must be a list of strings")
        for check in checks:
            validate_check(check, case_id)
        seen.add(case_id)
        cases.append(case)
    if not cases:
        raise UserError("The case file is empty")
    return cases


def check_response(response: str, checks: list[dict]) -> list[dict]:
    parsed = MISSING
    attempted_parse = False
    results = []
    for check in checks:
        kind = check["type"]
        passed = False
        detail = ""
        if kind == "equals":
            passed = response == check["value"]
        elif kind == "contains":
            passed = check["value"] in response
        elif kind == "not_contains":
            passed = check["value"] not in response
        elif kind == "regex":
            passed = re.search(check["value"], response) is not None
        elif kind == "max_chars":
            passed = len(response) <= check["value"]
        else:
            if not attempted_parse:
                try:
                    parsed = json_loads(response)
                except ValueError:
                    parsed = MISSING
                attempted_parse = True
            if parsed is MISSING:
                detail = "response is not valid JSON"
            elif kind == "json_valid":
                passed = True
            else:
                actual = resolve_pointer(parsed, check["pointer"])
                if actual is MISSING:
                    detail = f"missing JSON pointer {check['pointer']!r}"
                elif kind == "json_pointer_exists":
                    passed = True
                elif kind == "json_pointer_type":
                    expected = check["value"]
                    if expected == "null":
                        passed = actual is None
                    elif expected == "number":
                        passed = type(actual) in (int, float)
                    else:
                        passed = type(actual) is {"boolean": bool, "string": str, "array": list, "object": dict}[expected]
                    if not passed:
                        detail = f"wrong JSON type at pointer {check['pointer']!r}; expected {expected}"
                else:
                    passed = json_equal(actual, check["value"])
                    if not passed:
                        detail = f"value differs at JSON pointer {check['pointer']!r}"
        results.append({"type": kind, "pass": passed, "detail": detail or ("ok" if passed else "check failed")})
    return results


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_endpoint(base_url: str) -> str:
    try:
        url = parse.urlsplit(base_url)
        _ = url.port
    except ValueError as exc:
        raise UserError("Base URL is malformed") from exc
    if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise UserError("Base URL must be an http(s) URL without credentials, query, or fragment")
    if url.scheme == "http":
        host = url.hostname.lower()
        try:
            local = host == "localhost" or ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = host == "localhost"
        if not local:
            raise UserError("Plain HTTP is allowed only for loopback addresses; use HTTPS for remote APIs")
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/chat/completions"


def api_complete(endpoint: str, key: str | None, model: str, prompt: str, user_input: str, timeout: float, temperature):
    payload = {"model": model, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": user_input}], "stream": False}
    if temperature is not None:
        payload["temperature"] = temperature
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key is not None:
        headers["Authorization"] = "Bearer " + key
    req = request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
    try:
        with request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            data = json_loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        raise UserError(f"Provider returned HTTP {exc.code}; response body omitted") from exc
    except (error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise UserError(f"Provider connection failed ({type(exc).__name__})") from exc
    except (UnicodeError, ValueError) as exc:
        raise UserError("Provider returned invalid JSON") from exc
    try:
        choice = data["choices"][0]
        if choice.get("finish_reason") in ("length", "content_filter"):
            raise UserError("Provider returned a truncated or filtered completion")
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("content is not text")
    except (TypeError, KeyError, IndexError, AttributeError) as exc:
        raise UserError("Provider did not return a text chat completion") from exc
    usage = data.get("usage") if isinstance(data, dict) else None
    safe_usage = {}
    if isinstance(usage, dict):
        for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if type(usage.get(name)) is int and usage[name] >= 0:
                safe_usage[name] = usage[name]
    return content, safe_usage


def write_json(path: Path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise UserError(f"Cannot write {path}: {exc}") from exc


def ensure_distinct_output(out: Path, inputs: list[Path]):
    if any(out.resolve() == item.resolve() for item in inputs):
        raise UserError("Output path must differ from all input files")


def run_suite(args) -> int:
    inputs = [args.cases, args.prompt]
    if args.mock_responses:
        inputs.append(args.mock_responses)
    ensure_distinct_output(args.out, inputs)
    cases = load_cases(args.cases)
    prompt = read_text(args.prompt)
    if not prompt.strip():
        raise UserError("System prompt is empty")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise UserError("Timeout must be positive")
    if args.temperature is not None and not 0 <= args.temperature <= 2:
        raise UserError("Temperature must be between 0 and 2")
    if args.backend == "mock":
        if not args.mock_responses:
            raise UserError("Mock backend requires --mock-responses")
        mocks = read_json(args.mock_responses)
        if not isinstance(mocks, dict):
            raise UserError("Mock responses must be an object mapping case IDs to strings")
        endpoint, key = None, None
        model = args.model or "mock"
    else:
        if args.mock_responses:
            raise UserError("--mock-responses is only for the mock backend")
        if not args.base_url or not args.model:
            raise UserError("API backend requires --base-url and --model")
        endpoint = api_endpoint(args.base_url)
        key = None if args.no_auth else os.environ.get(args.api_key_env)
        if not args.no_auth and not key:
            raise UserError(f"Missing API key in environment variable {args.api_key_env}")
        model = args.model
    results = []
    for case in cases:
        item = {"id": case["id"], "case_hash": digest(case), "status": "error", "checks": [], "latency_ms": None, "usage": {}}
        start = time.perf_counter()
        try:
            if args.backend == "mock":
                text = mocks.get(case["id"])
                if not isinstance(text, str):
                    raise UserError("Missing or non-string mock response")
                usage = {}
            else:
                text, usage = api_complete(endpoint, key, model, prompt, case["input"], args.timeout, args.temperature)
            item["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            item["checks"] = check_response(text, case["checks"])
            item["status"] = "pass" if all(c["pass"] for c in item["checks"]) else "fail"
            item["usage"] = usage
            if args.include_output:
                item["output"] = text
        except UserError as exc:
            item["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            item["error"] = str(exc)
        results.append(item)
        print(f"{item['status'].upper():5} {item['id']}")
    report = {"format": "caseprobe-run-v1", "version": VERSION, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "backend": args.backend, "model": model, "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "temperature": args.temperature, "results": results}
    write_json(args.out, report)
    counts = {status: sum(item["status"] == status for item in results) for status in ("pass", "fail", "error")}
    print(f"Results: {counts['pass']} passed, {counts['fail']} failed, {counts['error']} errors. Saved: {args.out}")
    return 2 if counts["error"] else (1 if counts["fail"] else 0)


def read_report(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, dict) or data.get("format") != "caseprobe-run-v1" or not isinstance(data.get("results"), list):
        raise UserError(f"Not a CaseProbe run report: {path}")
    seen = set()
    for item in data["results"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not ID_RE.fullmatch(item["id"]) or item.get("status") not in ("pass", "fail", "error") or not isinstance(item.get("case_hash"), str) or item["id"] in seen:
            raise UserError(f"Malformed or duplicate case in report: {path}")
        seen.add(item["id"])
    if not seen:
        raise UserError(f"Report has no cases: {path}")
    return data


def md_cell(value) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def compare_reports(args) -> int:
    if args.out:
        ensure_distinct_output(args.out, [args.baseline, args.candidate])
    baseline, candidate = read_report(args.baseline), read_report(args.candidate)
    old = {x["id"]: x for x in baseline["results"]}
    new = {x["id"]: x for x in candidate["results"]}
    regressions, improvements, existing, stable, incomparable = [], [], [], [], []
    for case_id in sorted(old.keys() | new.keys()):
        a, b = old.get(case_id), new.get(case_id)
        if a is None:
            incomparable.append((case_id, "added case"))
        elif b is None:
            incomparable.append((case_id, "removed case"))
        elif a["case_hash"] != b["case_hash"]:
            incomparable.append((case_id, "case definition changed"))
        elif "error" in (a["status"], b["status"]):
            incomparable.append((case_id, "provider or fixture error"))
        elif a["status"] == "pass" and b["status"] == "fail":
            regressions.append(case_id)
        elif a["status"] == "fail" and b["status"] == "pass":
            improvements.append(case_id)
        elif a["status"] == "fail":
            existing.append(case_id)
        else:
            stable.append(case_id)
    lines = ["# CaseProbe comparison", "", f"Baseline: `{md_cell(baseline.get('backend', '?'))}` / `{md_cell(baseline.get('model', '?'))}`; prompt SHA-256: `{md_cell(baseline.get('prompt_hash', '?'))}`; temperature: `{md_cell(baseline.get('temperature', 'unknown'))}`", f"Candidate: `{md_cell(candidate.get('backend', '?'))}` / `{md_cell(candidate.get('model', '?'))}`; prompt SHA-256: `{md_cell(candidate.get('prompt_hash', '?'))}`; temperature: `{md_cell(candidate.get('temperature', 'unknown'))}`", "", "| Outcome | Count |", "| --- | ---: |", f"| Regressions | {len(regressions)} |", f"| Improvements | {len(improvements)} |", f"| Still failing | {len(existing)} |", f"| Still passing | {len(stable)} |", f"| Incomparable | {len(incomparable)} |", ""]
    for heading, ids in (("Regressions", regressions), ("Improvements", improvements), ("Still failing", existing)):
        if ids:
            lines += [f"## {heading}", ""]
            for case_id in ids:
                failed = [c for c in new[case_id].get("checks", []) if isinstance(c, dict) and c.get("pass") is False]
                details = "; ".join(f"{md_cell(c.get('type', 'check'))}: {md_cell(c.get('detail', 'failed'))}" for c in failed)
                lines.append(f"- `{case_id}`" + (f": {details}" if details else ""))
            lines.append("")
    if incomparable:
        lines += ["## Incomparable cases", ""] + [f"- `{x}`: {reason}" for x, reason in incomparable] + [""]
    lines += ["A regression means a case changed from pass to fail. Changed cases and errors are not scored as regressions.", ""]
    output = "\n".join(lines)
    print(output)
    if args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(output, encoding="utf-8")
        except OSError as exc:
            raise UserError(f"Cannot write {args.out}: {exc}") from exc
    return 2 if incomparable else (1 if regressions else 0)


def build_parser():
    parser = argparse.ArgumentParser(description="Compare deterministic checks across LLM prompt or model changes.")
    parser.add_argument("--version", action="version", version=f"CaseProbe {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run a JSONL suite and write a JSON report")
    run.add_argument("--cases", type=Path, required=True)
    run.add_argument("--prompt", type=Path, required=True, help="system prompt text file")
    run.add_argument("--backend", choices=("mock", "api"), required=True)
    run.add_argument("--mock-responses", type=Path)
    run.add_argument("--base-url", help="OpenAI-compatible API base URL; use HTTPS except on loopback")
    run.add_argument("--model", help="model ID supported by the chosen chat-completions endpoint")
    run.add_argument("--api-key-env", default="OPENAI_API_KEY", help="name of environment variable containing API key")
    run.add_argument("--no-auth", action="store_true", help="send no Authorization header, e.g. local servers")
    run.add_argument("--timeout", type=float, default=60)
    run.add_argument("--temperature", type=float, default=None, help="omit unless supported by your model")
    run.add_argument("--include-output", action="store_true", help="store full model output in report")
    run.add_argument("--out", type=Path, required=True)
    compare = sub.add_parser("compare", help="compare two JSON reports")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--out", type=Path, help="optional Markdown output path")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_suite(args) if args.command == "run" else compare_reports(args)
    except UserError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
