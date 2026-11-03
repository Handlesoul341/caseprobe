# 用 CaseProbe 验证提示词修改

这个例子展示如何围绕业务失败调整提示词，并用同一组测试用例检查变化。示例中的退款规则是虚构的，模型表现需要实际测试；离线模拟响应不能证明某版提示词更好。

## 两个版本

- `examples/refund/system-prompt-weak.txt`：较简略，只说明 30 天内可申请，未明确超期、信息缺失和分类枚举值。
- `examples/refund/system-prompt.txt`：补充边界条件、信息缺失的处理方式、输出字段和枚举值，并要求忽略输入中修改规则的指令。

两个版本适合用来验证：明确业务规则和输出契约后，模型是否在你关心的用例上减少错误。更长的提示词不保证更好，也可能增加 token 消耗。

## 在 DeepSeek 上比较

设置 `DEEPSEEK_API_KEY` 环境变量后，在项目根目录运行以下命令。它们会调用真实 API 并可能产生费用；将模型名改成你账号中可用的 Chat Completions 模型。案例输入和提示词会发送给服务商。

```bash
python skills/caseprobe/scripts/caseprobe.py run --cases examples/refund/cases.jsonl --prompt examples/refund/system-prompt-weak.txt --backend api --base-url https://api.deepseek.com --model deepseek-flash --api-key-env DEEPSEEK_API_KEY --out results/prompt-v1.json

python skills/caseprobe/scripts/caseprobe.py run --cases examples/refund/cases.jsonl --prompt examples/refund/system-prompt.txt --backend api --base-url https://api.deepseek.com --model deepseek-flash --api-key-env DEEPSEEK_API_KEY --out results/prompt-v2.json

python skills/caseprobe/scripts/caseprobe.py compare --baseline results/prompt-v1.json --candidate results/prompt-v2.json --out results/prompt-diff.md
```

`run` 在存在测试失败时返回 1，存在接口错误时返回 2，但仍会保存报告。`compare` 返回 0 只表示没有新退化；报告中的「Still failing」仍需要处理。用例变更或接口错误被标为不可比较，比较命令返回 2。

## 如何判断

1. 看 `Improvements`、`Regressions` 和 `Still failing` 的具体用例，而不是只看总通过数。
2. 若需查看真实输出，可以在对应的 `run` 命令加入 `--include-output` 后重跑；生成的 JSON 可能包含敏感数据。
3. 固定其他设置，多次重复；保留未参与提示词调整的独立样本，并结合人工检查。数据分布不具代表性或检查规则本身错误时，通过率不能说明实际效果。
4. 在报告中参考接口返回的 token 用量（如果有）。CaseProbe 不计算成本，也不自动断言修改更省钱。

要比较两个模型时，反过来固定同一版提示词和用例，只改接口地址、模型与相应的 API Key。请参考服务商当前文档及模型权限；并非所有模型都支持相同参数。
