# CaseProbe

**Catch prompt and model regressions before your users do.**

[中文说明](README.zh-CN.md) · [Agent Skill](skills/caseprobe/SKILL.md) · [Prompt experiment](docs/PROMPT-OPTIMIZATION.zh-CN.md) · [Publishing guide](docs/PUBLISHING.zh-CN.md)

CaseProbe is a small Python CLI and Agent Skill for testing the output contract of an LLM application. Run the same cases against a baseline and a candidate, then see precisely which previously passing cases failed. For example, compare two versions of a support-bot prompt, or test a move from a GPT model to a DeepSeek model.

```text
Baseline: 5 passed    Candidate: 4 passed, 1 failed

Regressions: 1
  prompt_injection: json_pointer_equals: value differs at JSON pointer '/decision'
```

This is **synthetic demo data**, not a benchmark of any actual model.

- **Minimal setup:** Python 3.10+; the CLI uses only the standard library.
- **Useful checks:** exact or partial text, regex, valid JSON, JSON Pointer equality/existence/type, and response length.
- **Honest comparisons:** changed/added/removed cases, API errors, and truncated completions are incomparable, not silently counted as regressions.
- **Local-first workflow:** start with mock responses; real calls use a user-specified OpenAI-compatible Chat Completions endpoint.
- **Reusable skill:** an assistant can help design cases, run comparisons, and interpret failures.

## Quick start: offline

Download and unzip the repository, open a terminal in its root, then run:

```bash
python examples/refund/demo.py
```

The example runs five fictitious refund-policy cases against two hand-written mock response sets. The second set intentionally fails one case. The resulting Markdown and JSON files are written to `results/refund-demo/` (ignored by Git); a [sample report](docs/demo-report.md) is also included. No model or network is used. The demo command itself exits 0 when it successfully demonstrates the expected regression.

## Compare real models

Set `OPENAI_API_KEY` and `DEEPSEEK_API_KEY` in your environment first. Calls send the system prompt and case inputs to the chosen provider and may incur charges. Choose Chat Completions model IDs that your account can use. These IDs are examples, not an assertion that either model is better.

```bash
python skills/caseprobe/scripts/caseprobe.py run --cases examples/refund/cases.jsonl --prompt examples/refund/system-prompt.txt --backend api --base-url https://api.openai.com/v1 --model gpt-5.4-mini --api-key-env OPENAI_API_KEY --out results/openai.json

python skills/caseprobe/scripts/caseprobe.py run --cases examples/refund/cases.jsonl --prompt examples/refund/system-prompt.txt --backend api --base-url https://api.deepseek.com --model deepseek-flash --api-key-env DEEPSEEK_API_KEY --out results/deepseek.json

python skills/caseprobe/scripts/caseprobe.py compare --baseline results/openai.json --candidate results/deepseek.json --out results/comparison.md
```

For a prompt-only experiment, use the same model, endpoint, cases and settings for both runs, and change only `--prompt`. For a model comparison, hold the prompt and cases constant. Pin model snapshots when your provider offers them; repeat runs and review variability before deciding on a deployment. Optional `--temperature` is sent only if explicitly supplied and supported by the model. There is no automatic retry or parallelism.

The refund example includes a deliberately underspecified `system-prompt-weak.txt` and a more explicit `system-prompt.txt`; use real model runs to assess whether that change helps your use case. The [prompt experiment guide](docs/PROMPT-OPTIMIZATION.zh-CN.md) contains a complete DeepSeek example in Chinese.

The API adapter uses non-streaming text `POST /chat/completions`, common to the two examples above. It is not the OpenAI Responses API and does not support images, tool calls or vendor-specific fields. Other compatible endpoints and model IDs need independent verification. For a local server without authentication, use a loopback `http://` base URL plus `--no-auth`. Remote plain HTTP is refused; redirects are not followed.

## Write your own suite

Use one JSON object per line in a UTF-8 `.jsonl` file. IDs must be unique and use ASCII letters, digits, `.`, `_`, or `-`. `input` is the user message, and `--prompt` supplies a system message. All checks on a case must pass.

```json
{"id":"refund_30_days","input":"Delivered 30 days ago; can I request a refund?","checks":[{"type":"json_valid"},{"type":"json_pointer_equals","pointer":"/decision","value":"eligible"}]}
```

| Check | Required fields | Meaning |
| --- | --- | --- |
| `equals` | `value` (string) | Exact entire response |
| `contains`, `not_contains` | `value` (string) | Case-sensitive substring |
| `regex` | `value` (string) | Python regex search |
| `json_valid` | — | Strict JSON; markdown fences fail |
| `json_pointer_exists` | `pointer` | JSON Pointer exists, including a `null` value |
| `json_pointer_equals` | `pointer`, `value` | JSON Pointer value equals a JSON value |
| `json_pointer_type` | `pointer`, `value` | JSON type: `null`, `boolean`, `number`, `string`, `array`, or `object` |
| `max_chars` | `value` (integer) | Maximum Unicode code points |

JSON Pointers support nesting, array indices, and RFC 6901 `~0`/`~1` escapes. `tags` can be attached to cases as an optional array of strings; changing any case field makes that case incomparable with an old run. For offline testing, the mock fixture is a single JSON object mapping case IDs to output strings; see the examples.

Reports contain case IDs, hashes, check results, latency, and provider-reported token usage if available. Full model responses are omitted unless `--include-output` is supplied. Review reports and case IDs for sensitive data before sharing or committing them. The CLI does not calculate prices; cached-token rates and pricing vary by provider.

## Exit codes and CI

| Command | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `run` | All cases passed | At least one case failed, no errors | Invalid input or at least one provider/fixture error |
| `compare` | No regressions and all cases comparable | At least one pass → fail regression | Invalid report or at least one incomparable case |

Run reports are written even if a case fails or an API call errors. A `compare` exit code of 0 means no regressions, not necessarily that every case passed: inspect any still-failing cases. `compare` requires the exact same case definitions, not merely identical IDs. Inspect incomparable cases before deciding whether a result is safe to use. The repository's CI exercises offline behavior and a local fake HTTP endpoint; it does not require API credentials.

## Install the Agent Skill

Copy the entire `skills/caseprobe` directory into the skills directory supported by your agent. For Codex, a user-level location is `~/.codex/skills/` (Windows: `%USERPROFILE%\.codex\skills\`). For a fresh installation on macOS/Linux:

```bash
mkdir -p ~/.codex/skills
cp -R skills/caseprobe ~/.codex/skills/
```

Restart the agent if needed, then ask: “Use CaseProbe to build regression cases for this prompt and compare the two versions.” Do not overwrite an existing skill without reviewing it. The script is bundled inside the skill, so copying the folder is sufficient. Discovery and paths may differ in other Agent Skills-compatible products.

## Scope and related work

CaseProbe is a small starter for deterministic output contracts, not a replacement for a comprehensive evaluation platform. It does not provide semantic scoring, an LLM judge, JSON Schema validation, agent trace evaluation, or a security guarantee. Model outputs can vary even with the same settings, and a passing small suite is not proof of general quality. Check representative data and use human review where needed.

For a broader evaluation and red-teaming platform, see [Promptfoo](https://github.com/promptfoo/promptfoo). The skill follows the [Agent Skills specification](https://agentskills.io/specification). API references: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) and [DeepSeek API](https://api-docs.deepseek.com/).

## Test

```bash
python -m unittest discover -s tests -v
```

MIT licensed; see [LICENSE](LICENSE).
