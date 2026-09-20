# Work Governance

[English](README.md) | **简体中文**

**为 Codex 提供可组合的治理层：增加判断力，而不增加形式主义。**

Work Governance 帮助 Agent 发现真实目标，只引入任务确实需要的协调机制，保护授权边界，并让完成声明与证据强度相匹配。清晰的工作应当持续推进；Plan、SubAgent、独立审查和持久化状态只在能够创造价值时才加入。

由 [feng2r200](https://github.com/feng2r200) 创建并维护。

## 为什么需要它

能力强大的 Agent 通常不是因为缺少另一套强制工作流而失败，而是因为它们：

- 解决了被提出的实现方式，却没有解决真正的目标；
- 把每项任务都变成 Plan 或委派树；
- 把拥有可用凭证误认为获得了 push、发布或部署的授权；
- 因非阻塞性发现而中断有价值的执行；
- 没有核对当前证据，就把历史记录提升为项目事实；
- 或者让完成声明超出实际验证能够支持的范围。

Work Governance 将这些问题拆分为彼此独立的政策模块，而不是构造一个单体流程引擎。

## 它有什么不同

- **价值驱动：** 不会仅仅因为任务规模大或重要，就强制要求 Plan、SubAgent、工具调用或审查。
- **工具中立：** Plugin 不内置状态引擎、不要求某个特定 CLI，并把持久化提供方保留为独立能力。
- **理解授权边界：** 本地改动、commit、push、release、部署、生产操作和破坏性清理始终是不同的授权边界。
- **按证据校准：** 验证会随声明范围和风险扩展，而不是固化成一套测试仪式。
- **可组合：** 每个 Skill 只负责一种判断，也可以独立使用。

```text
用户目标与授权
      |
      v
work-lifecycle 路由器
      |
      +-- 目标发现
      +-- Plan 治理
      +-- SubAgent 治理
      +-- Git 边界
      +-- 独立验证
      +-- 项目事实
      +-- 归档整理
      +-- 工作汇报
      |
      v
现有工具与项目专用 Skill
```

## 模块

| Skill | 负责的判断 |
| --- | --- |
| `work-lifecycle` | 小型路由器与安全内核 |
| `goal-discovery` | 目标澄清与最小决策边界 |
| `plan-governance` | Plan 准入、No-Plan 演进和实质性修订 |
| `subagent-governance` | 委派价值、所有权和整合 |
| `git-change-governance` | 分支、worktree、commit 和远端边界 |
| `independent-validation` | 与风险相匹配的独立质疑 |
| `project-truth-governance` | 事实来源选择与审慎提升 |
| `project-archive-curation` | 保留位置与归档就绪判断 |
| `work-reporting` | 进度、交接和完成汇报 |

## 安装

先将 GitHub 仓库添加为 Codex Plugin marketplace，再安装 Plugin：

```sh
codex plugin marketplace add feng2r200/codex-work-governance
codex plugin add work-governance@work-governance-local
```

如果从当前 checkout 进行本地开发：

```sh
codex plugin marketplace add .
codex plugin add work-governance@work-governance-local
```

安装或更新后，请新建一个 Codex 任务。已有任务可能继续保留其启动时加载的 Skill 内容。

## 行为示例

面对一个可直接执行的缺陷修复，Work Governance 应当让 Agent 直接检查、实现并运行针对性测试，而不是要求先创建 Plan。如果同一任务后来扩展为必须跨交接持续推进的多个依赖阶段，Agent 可以在那时创建一次 Plan，并继承已经发现的有效结论、约束和证据。

如果仓库存在未提交改动，Git 模块会保护无关工作。如果本地验证已经通过，但 push 尚未获得授权，汇报模块会说明本地已验证的结果，并保持远端不变。

## 包结构

可分发 Plugin 位于 `plugins/work-governance`，其中使用：

- `plugin.json` 作为可移植的 Agent Plugins manifest；
- `.codex-plugin/plugin.json` 作为 Codex 兼容性后备 manifest；
- `skills/` 存放九个相互独立的政策模块；
- `.agents/plugins/marketplace.json` 作为仓库 marketplace。

可移植 manifest 是面向未来的包权威来源。测试会确保它的身份信息和 OpenAI 接口元数据与兼容性 manifest 保持一致。

## 验证

安装开发依赖并运行政策契约测试：

```sh
uv sync --locked --all-groups
uv run pytest
uv run ruff check tests/test_policy_contract.py
```

如果本地可以使用 Codex 自带的验证器，还应运行：

```sh
SKILL_VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
PLUGIN_VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py"

for skill in plugins/work-governance/skills/*; do
  test -f "$skill/SKILL.md" || continue
  uv run --with pyyaml python "$SKILL_VALIDATOR" "$skill"
done

uv run --with pyyaml python "$PLUGIN_VALIDATOR" plugins/work-governance
git diff --check
```

当前测试套件保护具有代表性的政策边界和打包一致性。它还不是一套已经发布、用于衡量 Agent 实际效果的行为基准；这是一个有意保留并明确记录的区别，而不是被隐藏的缺口。

## 贡献与安全

提出政策变更前请阅读 [CONTRIBUTING.md（英文）](CONTRIBUTING.md)。安全问题请通过 [SECURITY.md（英文）](SECURITY.md)报告，并使用 [SUPPORT.md（英文）](SUPPORT.md)选择合适的支持渠道。

## 许可证

本项目采用 Apache License 2.0，详见 [LICENSE](LICENSE)。
