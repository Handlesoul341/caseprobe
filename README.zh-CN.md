# CaseProbe

**在提示词或模型切换之前，先找出哪些业务用例会退化。**

[English](README.md) · [Skill 文件](skills/caseprobe/SKILL.md) · [提示词优化实战](docs/PROMPT-OPTIMIZATION.zh-CN.md) · [GitHub 发布指南](docs/PUBLISHING.zh-CN.md)

CaseProbe 是一个由 Python 命令行工具和 Agent Skill 组成的轻量项目。它对同一组业务用例分别运行基线与候选版本，并指出哪些用例从「通过」变成了「失败」。

适合客服分类、结构化信息抽取、RAG 答案格式检查等有明确输出规则的场景。你可以比较两版提示词，也可以比较 GPT、DeepSeek 或其他兼容 Chat Completions 的接口。

```text
基线：5 个通过     候选：4 个通过、1 个失败

退化：1 个
  prompt_injection：JSON 字段 /decision 的值不符合预期
```

上面是**人工构造的演示数据**，不是对真实模型的测试结论。

## 一分钟离线体验

要求 Python 3.10 或更高版本，不需要安装第三方 Python 包、API Key 或联网。

解压项目后，在项目根目录运行：

```bash
python examples/refund/demo.py
```

示例包含五个虚构的退款场景：普通、超期、临界日期、信息缺失和指令干扰。基线与候选响应均由人工预先写好，其中候选版本故意让一个用例失败。运行后查看 `results/refund-demo/comparison.md`，也可以直接查看[示例报告](docs/demo-report.md)。

## 接入 GPT 和 DeepSeek

先在当前终端设置自己的 API Key。以下为 PowerShell 示例，输入时不会明文回显：

```powershell
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'OpenAI API key' -AsSecureString)).Password
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'DeepSeek API key' -AsSecureString)).Password
```

然后在项目根目录运行：

```bash
python skills/caseprobe/scripts/caseprobe.py run --cases examples/refund/cases.jsonl --prompt examples/refund/system-prompt.txt --backend api --base-url https://api.openai.com/v1 --model gpt-5.4-mini --api-key-env OPENAI_API_KEY --out results/openai.json

python skills/caseprobe/scripts/caseprobe.py run --cases examples/refund/cases.jsonl --prompt examples/refund/system-prompt.txt --backend api --base-url https://api.deepseek.com --model deepseek-flash --api-key-env DEEPSEEK_API_KEY --out results/deepseek.json

python skills/caseprobe/scripts/caseprobe.py compare --baseline results/openai.json --candidate results/deepseek.json --out results/comparison.md
```

模型 ID 是示例，请根据账号权限及服务商最新文档替换。真实运行会将系统提示词和用例输入发送给指定服务商，并可能产生 API 费用。每次调用按顺序执行，不自动重试；使用 `--temperature` 时需确认模型支持该参数。

如果比较提示词，建议固定模型、接口、用例与参数，只修改 `--prompt`。如果比较模型，固定提示词和用例。结果会受模型随机性和模型版本变化影响，应重复试验并结合人工判断。

项目附带较简略的 `system-prompt-weak.txt` 和规则更明确的 `system-prompt.txt`，可按[提示词优化实战](docs/PROMPT-OPTIMIZATION.zh-CN.md)比较两版。离线演示是预设回复，不能据此证明哪版提示词更好。

此版本仅支持非流式文本 Chat Completions；**不支持 OpenAI Responses API、图片、工具调用和厂商特有参数**。支持该协议的其他服务也需要自行验证。无认证的本地服务可使用回环地址 `http://127.0.0.1:端口/v1` 和 `--no-auth`。

## 编写自己的用例

一个 UTF-8 JSONL 文件中，每行放一个 JSON 对象。`id` 必须唯一，只能使用英文字母、数字、`.`、`_`、`-`；`input` 是用户输入；所有 `checks` 都通过才算该用例通过。

```json
{"id":"refund_30_days","input":"已送达 30 天，可以退款吗？","checks":[{"type":"json_valid"},{"type":"json_pointer_equals","pointer":"/decision","value":"eligible"}]}
```

| 检查类型 | 用途 |
| --- | --- |
| `equals` | 整段文本与 `value` 完全相同 |
| `contains` / `not_contains` | 包含或不包含指定字符串，区分大小写 |
| `regex` | 按 Python 正则表达式搜索 |
| `json_valid` | 验证严格 JSON；Markdown 代码围栏会导致失败 |
| `json_pointer_exists` | 检查 JSON Pointer 对应字段存在，值为 `null` 也算存在 |
| `json_pointer_equals` | 检查 JSON Pointer 对应字段的值 |
| `json_pointer_type` | 检查字段类型：`null`、`boolean`、`number`、`string`、`array` 或 `object` |
| `max_chars` | 限制 Unicode 字符数 |

JSON Pointer 支持嵌套字段、数组索引以及 `~0`、`~1` 转义。可选 `tags` 是字符串数组。比较时如用例内容有任何变化，或用例被新增、删除，会标为「不可比较」，不会误判为模型退化。

报告默认包含用例 ID、哈希、检查结果、耗时，以及接口返回的 token 用量（若有）；不保存完整模型回复。如需排查可加 `--include-output`，但回复可能包含敏感内容。分享或提交报告前，请检查用例 ID 和报告内容。项目不估算费用。

## 安装 Skill

将整个 `skills/caseprobe` 文件夹复制到支持 Agent Skills 的工具对应目录。以 Windows 上的 Codex 为例，在项目根目录的 PowerShell 中运行：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse ".\skills\caseprobe" "$env:USERPROFILE\.codex\skills\caseprobe"
```

如果目标已有同名 Skill，请先检查，避免覆盖。必要时重启 Codex，然后输入：

> 使用 CaseProbe 为这个提示词设计回归用例，并比较修改前后的表现。

脚本随 Skill 文件夹一起打包，复制整个文件夹即可；不同产品的技能发现方式和安装目录可能不同。

## 结果与退出码

| 命令 | 退出码 0 | 退出码 1 | 退出码 2 |
| --- | --- | --- | --- |
| `run` | 所有用例通过 | 存在失败，且无接口错误 | 输入错误或存在接口/模拟数据错误 |
| `compare` | 无退化且全部可比较 | 存在通过变失败的退化 | 报告无效或存在不可比较的用例 |

模型回复被截断、被过滤、接口报错或模拟数据缺失时，结果为错误，不计作通过或退化。运行时即使出现单个用例失败或接口错误，也会保存报告。`compare` 返回 0 只表示没有新退化，基线已失败的用例仍可能失败，需查看报告。

## 项目边界

CaseProbe 的定位是便于理解和修改的确定性输出检查工具。它尚不支持语义评分、LLM 裁判、完整 JSON Schema 校验、Agent 轨迹评估，也不能保证抵御提示词注入。少量用例通过不代表模型整体更好或适合直接上线。

如果需要更完整的评测与红队能力，可参考 [Promptfoo](https://github.com/promptfoo/promptfoo)。Skill 格式参考 [Agent Skills 规范](https://agentskills.io/specification)，接口参考 [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) 和 [DeepSeek 官方文档](https://api-docs.deepseek.com/)。

## 运行自动化测试

```bash
python -m unittest discover -s tests -v
```

测试使用模拟数据和本机假接口，不需要模型服务的 API Key。项目采用 MIT 协议，详见 [LICENSE](LICENSE)。
