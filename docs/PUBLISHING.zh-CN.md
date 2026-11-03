# 发布到 GitHub

## 发布前

1. 解压项目，在项目根目录运行 `python examples/refund/demo.py` 和 `python -m unittest discover -s tests -v`。
2. 阅读中英文 README，根据需要修改项目名称、定位和示例。
3. 检查准备提交的文件：不要提交 API Key、真实用户数据、含敏感信息的报告。仓库已忽略 `.env` 和 `results/`，但仍应检查暂存内容。
4. 阅读 `LICENSE`。当前采用 MIT 许可证，版权行可以改成你的姓名、团队或公司名称；如果修改，同时更新独立 Skill 内的 `skills/caseprobe/LICENSE`。发布前确认你愿意采用该许可证。

## 用 Git 推送

先在 GitHub 网页上创建一个空仓库，例如 `caseprobe`；不要在网页上额外初始化 README、许可证或 `.gitignore`，以免与本地文件冲突。然后在项目根目录执行：

```bash
git init
git add .
git status
git commit -m "Initial release of CaseProbe"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/caseprobe.git
git push -u origin main
```

将 `YOUR_USERNAME` 换成你的 GitHub 用户名；如果仓库名称不同，也要调整地址。GitHub 可能要求通过浏览器或令牌认证。`git status` 可用于推送前核对文件。仓库中的 `.github/workflows/ci.yml` 会在 GitHub Actions 上运行离线测试；它不需要配置模型 API Key。

## 仓库介绍建议

Description：

> Catch prompt and model regressions with a zero-dependency Python CLI and reusable Agent Skill.

Topics 可以考虑：`llm-evaluation`、`prompt-testing`、`agent-skills`、`deepseek`、`openai`、`llmops`、`python`。

发布时可以说明：这是可运行的首个版本，主要覆盖文本与 JSON 合约检查；案例演示使用模拟数据，真实供应商测试需要使用者自己的 API Key。不要将模拟结果宣传为真实模型的能力排名或性能提升。

## 后续演进建议

- 用经过脱敏的真实业务失败样本扩充用例集，并持续维护标准答案。
- 根据使用反馈增加重复采样、延迟汇总和成本配置；实现后再公开宣称支持。
- 根据需要接入 Responses API、JSON Schema 或 CI 报告摘要。
