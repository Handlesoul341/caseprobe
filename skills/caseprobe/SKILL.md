---
name: caseprobe
description: Design and run small, deterministic regression checks for text or JSON responses from chat-completions models. Use when comparing a prompt change, GPT and DeepSeek, or two OpenAI-compatible endpoints on the same concrete cases.
license: MIT
---

# CaseProbe

Turn a real LLM application's output contract into repeatable examples. The bundled `scripts/caseprobe.py` uses only Python 3.10+ standard library. When invoking it, resolve the script relative to this skill directory; the skill works independently of the original repository.

1. Identify the real system prompt, sample inputs, expected behavior, and a meaningful baseline. Do not invent ground truth from model answers. Prefer small, anonymized cases that include ordinary requests, missing information, boundary cases, and known past failures. Keep model and prompt changes separate when diagnosing a regression.
2. Write a UTF-8 JSONL suite: one object per line with unique ASCII `id`, `input`, and a nonempty `checks` list. Checks are conjunctive. Supported checks:
   - `{"type":"equals","value":"..."}`, `contains`, `not_contains`, and `regex` (Python regular expressions, case-sensitive).
   - `{"type":"json_valid"}` for strict JSON; `{"type":"json_pointer_exists","pointer":"/field"}`; `{"type":"json_pointer_equals","pointer":"/field","value":"expected"}`; and `{"type":"json_pointer_type","pointer":"/field","value":"string"}`. Type values are `null`, `boolean`, `number`, `string`, `array`, or `object`. Pointers follow RFC 6901, including array indices and `~0`/`~1` escapes.
   - `{"type":"max_chars","value":500}` counts Unicode code points.
3. Write the system prompt to a UTF-8 text file. Run the same suite for baseline and candidate. The exact JSONL case definitions must match between reports. Use a mock fixture for an offline demonstration, or use `--backend api --base-url URL --model MODEL --api-key-env KEY_ENV` when the user has chosen a compatible endpoint and authorized sending the selected data. The script sends each case and the prompt to that endpoint; local APIs can opt out of authentication with `--no-auth`.
4. Compare with `compare --baseline OLD.json --candidate NEW.json --out comparison.md`. Exit codes: 0 means no regressions, 1 means at least one passing case became failing, 2 means an error or incomparable cases. A case whose definition changed, appeared or disappeared, or had a provider error is incomparable, not a pass or regression. Preserve such evidence and resolve it before drawing a conclusion.
5. Explain the failed checks, inspect outputs only if saved with `--include-output`, propose a specific prompt or model change, and rerun. A comparison with no regressions can still contain previously failing cases. Reports omit response text by default; opting in may save sensitive content. Fixed text checks are not semantic grading, and a small suite cannot prove a model is generally better. Recommend human review for open-ended or safety-sensitive answers.

## Commands

Replace `<script>` with this skill's `scripts/caseprobe.py`; paths are local files:

```bash
python <script> run --cases cases.jsonl --prompt prompt.txt --backend mock --mock-responses responses.json --out baseline.json
python <script> run --cases cases.jsonl --prompt prompt.txt --backend api --base-url https://api.deepseek.com --model <model-id> --api-key-env DEEPSEEK_API_KEY --out candidate.json
python <script> compare --baseline baseline.json --candidate candidate.json --out comparison.md
```

Mock responses are one JSON object mapping case IDs to output strings. `--include-output` must be set on the run whose full output needs inspection. Runs are sequential, do not retry, and can incur provider charges. Only send data the user intends to share with that provider; never put API keys in case files, prompts, reports, or commands.
