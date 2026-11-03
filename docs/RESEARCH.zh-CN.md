# 选题调研记录

检索日期：2026-11-03。GitHub 排名和 star 会变化，以下内容是方向参考，不代表对产品需求的定量验证。

| 参考 | 观察 | 对 CaseProbe 的启发 |
| --- | --- | --- |
| [GitHub Trending](https://github.com/trending) | 检索时列表包含 Agent、跨会话上下文和 Skill 相关仓库，例如 `mattpocock/skills`。 | 提供可被 Agent 复用的 Skill，同时解决具体工作流。 |
| [anthropics/skills](https://github.com/anthropics/skills) | 公开仓库展示按 Skill 文件夹组织的分发方式。 | 使用 `skills/caseprobe/SKILL.md`，并把运行脚本一起打包。 |
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | 成熟项目覆盖模型评测、提示词测试和红队等功能。 | 聚焦可读、无第三方依赖、可离线演示的小型回归工作流；并不宣称首创或功能更全。 |
| [Agent Skills specification](https://agentskills.io/specification) | 描述了 `SKILL.md` 的基本结构和元数据。 | 采用规范格式，确保必要元数据和技能脚本随包交付。 |
| [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) / [DeepSeek API](https://api-docs.deepseek.com/) | 均提供 Chat Completions 接口格式，但模型及参数支持可能不同。 | 以统一的基础文本请求完成跨供应商实验；具体模型兼容性和真实表现仍需实测。 |

CaseProbe 的设计取舍是把问题收窄到「同一组业务用例上，什么从通过变成失败」。它不是模型训练方法，也不宣称单靠 Skill 就能提升 GPT 或 DeepSeek 本身的能力。
