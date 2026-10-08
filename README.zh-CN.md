# Work Governance

[English](README.md) | **简体中文**

**为 Codex 提供可组合的治理层：增加判断力，而不增加形式主义。**

Work Governance 帮助 Agent 发现真实目标，只引入任务确实需要的协调机制，保护授权边界，并让完成声明与证据强度相匹配。它也让已经加入治理的长期项目开发保持可恢复，而不会把这套机制强加给一次性工作。清晰的工作应当持续推进；Plan、SubAgent、独立审查和持久化状态只在能够创造价值时才加入。

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
- **核心工具中立：** 生命周期与政策模块不内置状态引擎，也不要求某个特定 CLI。可选工具适配模块彼此隔离、按场景触发，并能在不可用时降级而不阻塞无关工作。
- **理解授权边界：** 本地改动、commit、push、release、部署、生产操作和破坏性清理始终是不同的授权边界。
- **按证据校准：** 验证会随声明范围和风险扩展，而不是固化成一套测试仪式。
- **自适应：** 在依赖工作开始前对齐实质选择；出现新证据时，只执行其影响所需的回看与纠偏。
- **可组合：** 每个 Skill 只负责一种判断，也可以独立使用。

## 自适应工作闭环

Work Governance 会在执行路线被固化前，区分可调查事实、普通实现细节与用户拥有的实质选择。默认模式下，实质选择进入精简的用户确认门；当用户明确把当前任务或阶段内的判断权委托给 Codex 后，Codex 在“决策权包络”内自行选择并继续，不制造不必要的停顿。

```text
对齐目标、证据、约束与授权
             |
     +-------+-------+
     |       |       |
 可调查事实  可逆细节  实质选择
   调查      自主决定  默认：确认
                    委托：自主决定
             |
       最小可验证切片
             |
          语义事件
             |
     有界回看、纠偏与再验证
```

语义事件包括新证据、关键假设失效、验证失败、里程碑完成、范围或相关外部状态变化，以及回执与实际状态不一致。显式委托生效时，Codex 可以在包络内自主修复、回退、替换或重排路线、修订 Plan、扩大验证；只有纠偏必须改变目标、超出委托范围、进入未授权环境或使用未列明受保护动作时，才重新进入用户确认门。委托转移的是判断权，不会取消证据责任，也不会默许 push、release、部署、生产、数据、凭证或破坏性操作。

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
      +-- 代码智能（可选适配）
      +-- 独立验证
      +-- 项目开发连续性
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
| `code-intelligence` | 结构化源码路由与按活动 checkout 安全建立 CodeGraph 就绪条件 |
| `independent-validation` | 与风险相匹配的独立质疑 |
| `project-development-governance` | 长期项目入口、恢复与状态对账 |
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

当开发任务需要理解符号、调用路径、影响范围、受影响测试或跨层关系时，可选的代码智能模块会检查精确的活动 checkout。如果本机 CodeGraph 可用，但该 checkout 尚无索引，它可以先创建并回读验证本地派生索引，再开始查询。字面文本、文档、日志、配置、不支持的内容以及明确只读的位置仍使用原生检查路径。该适配模块不会把索引当成项目事实，也不会静默安装全局工具。

如果同一目标存在会实质改变结果、边界、成本、风险或验收方式的不同方案，目标发现模块会在阶段 Plan 固化任一路线之前暴露这个方向选择。它可以核验前提与约束以形成建议，但不会等到某个未经确认的方案失败后才提问。用户已经明确选择方案时，只继续完成当前切片需要的有界可行性核验。

如果用户明确委托当前任务或阶段内的方向选择，目标发现模块会比较同样的实质影响，并直接选取有证据支持的路线。之后出现语义事件时，只要纠偏仍在该包络内，就可以自主完成；委托被撤销、到期或动作越界时，相应确认门恢复。状态没有真实变化时，不重复读取、评审、汇报或持久化写入。

对于已经加入治理的长期项目，项目开发模块会先读取一个小型路由入口，再只读取当前任务需要的有限状态和权威内容。任务收尾时，它会把有实质变化的进展、优先级、决策、风险和验收证据对账到唯一一个可变执行状态提供方。目标、架构、约束和验收仍由项目原生权威承载，项目契约也不会强制创建任务 Plan。

稳定的提供方定位符不会被误当成“状态只属于一个逻辑项目”的证明。共享且未分区的状态只能作为候选上下文，在隔离得到验证前禁止向提供方写入。恢复一个有界快照后，状态未变时直接复用；精确的变更回执与目标回读可以替代立即执行的大范围重读，而归属、路由、版本头、范围、证据、外部写入或回读不一致只会先重新打开受影响的路径。

当提供方具备只读的综合健康或就绪视图时，治理层优先复用这一个有界快照，而不重复执行等价的细分状态检查。路由干净未激活或能力缺失，只让对应操作处于降级状态；陈旧、损坏、歧义或完整性失败的控制状态会阻断受影响的提供方路径。两者都不会自动授予激活或修复权限。

提供方状态证据记录在 [提供方控制面效率同步证据](docs/validation/provider-control-plane-efficiency-v1.md) 中。CodeGraph 的职责归属、就绪条件、验证范围与采纳边界记录在 [代码智能适配模块采纳证据](docs/validation/code-intelligence-adoption-v1.md) 中。自适应决策委托与语义回看合同记录在 [自适应决策与回看闭环证据](docs/validation/adaptive-decision-and-review-loop-v1.md) 中。组合源码、当前本机生效状态与远端交付记录在 [代码智能与自适应治理组合交付证据](docs/validation/integrated-code-intelligence-adaptive-delivery-v1.md) 中。

## 包结构

可分发 Plugin 位于 `plugins/work-governance`，其中使用：

- `plugin.json` 作为可移植的 Agent Plugins manifest；
- `.codex-plugin/plugin.json` 作为 Codex 兼容性后备 manifest；
- `skills/` 存放十个相互独立的政策模块，以及一个可选的代码智能适配模块；
- `.agents/plugins/marketplace.json` 作为仓库 marketplace。

可移植 manifest 是面向未来的包权威来源。测试会确保它的身份信息和 OpenAI 接口元数据与兼容性 manifest 保持一致。

## 验证

安装开发依赖并运行政策契约测试：

```sh
uv sync --locked --all-groups
uv run pytest
uv run ruff check tests/test_policy_contract.py
uv run ruff format --check tests/test_policy_contract.py
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
