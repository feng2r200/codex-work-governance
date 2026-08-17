# 模型优先读这个

这页是面向模型的短入口。完整参数以 `docs/CLI_REFERENCE.md` 和
`workctl help <workflow>` 为准。

## 快速路径

- 使用安装后可直接执行的 `workctl` 作为运行入口；普通 schema-v5 工作不依赖
  SessionStart 或 UserPromptSubmit Hook。Plan authority、旧 schema refresh、风险事实
  和写入边界都以 controller 命令输出为准。如果 `workctl` 在 controller 启动前
  因旧插件缓存路径缺失而失败，先按 stale local installation shim 处理：用
  `command -v workctl`、`codex plugin list --json` 和只读的当前源码或已启用缓存
  `scripts/workctl doctor` 定位 mismatch；修复或重装注册入口前，不要用推导出的
  source/cache 路径执行 Plan mutation。
- 无 active Plan 且需要治理执行时，优先用
  `goal init --stdin|--from-file`。输入最小目标契约，controller 生成
  schema-v5 Plan、runtime state、event ledger 和 index。
- 只需要记录执行路径调整时，用
  `plan adapt --intent-stdin|--intent-from-file`。不要先手写 strict
  adaptation manifest，除非确实需要低层精确 patch。当前 active Plan 仍是
  schema-v4 时，需要同时带 `--expected-revision`、当前 turn receipt 和
  `--expected-intake-sha256`；schema-v5 的普通 intent 记录不需要这些 v4
  intake 参数。
- 任务完成且证据就是当前输出或文件时，用
  `task done --task-id T-001 --evidence-stdin|--from-file`。它会记录 direct
  evidence、生成 canonical Plan evidence，并完成 task verify。
- 结束 schema-v5 Plan 前，用 `plan closeout-check` 读取 runtime-backed
  readiness；任务状态来自 runtime state，不来自 frontmatter。ready 后用
  `plan complete --expected-state-sequence <state_sequence>`，不要传 v4
  `--expected-revision` 或当前 intake 参数。完成会释放 active pointer，下一轮
  新工作从 `UNMANAGED_EMPTY` 重新 `goal init`。
- 查旧 Plan 时，用 `plan history list|show`。这是宽松只读读取，不用旧历史
  格式约束当前 active schema；常规路径里的历史 `Plan.md` 会作为
  `NON_AUTHORITY` 候选显示，不能替代 `.work-governance/_Plan/index.yaml`
  指向的当前 active Plan。
- active Plan 只有插件当前声明的 schema-v5 可继续写。遇到 V3/V4 或任何
  非当前 schema 的 active Plan 时，只做只读摘要，然后用
  `migrate apply --expected-contract-revision <revision>` 归档旧 Plan 并重建
  schema-v5 contract；不要做状态适配、旧 task 状态迁移或
  `plan contract upgrade`。
- `legacy_summary` 和 `plan status.legacy_refresh` 只是 `NON_AUTHORITY`
  读取提示，用来帮助选择刷新后的下一步；不要把其中的旧 task status、
  confirmation 或 evidence 当成当前 runtime state。
- 判断高影响动作前，可用 `risk inspect --action-kind KIND --target-ref REF`
  获取风险事实。controller 不替模型决定是否必须向用户确认。
- 需要把上下文交给实现、检查、评审或项目真理源角色时，用
  `context build --role implement|check|review|truth --manifest PATH|--stdin`。
  manifest 只列项目内显式文件；输出包含 SHA256、截断状态和 bounded content。
  该命令只读、无 hook、不创建 Plan，也不改 runtime state。
- 子 worktree 执行只记录
  `worktree begin|record|close`。`begin` 会记录父 Plan `fork_base`；`close`
  会输出带 fork 基线的 close summary。完成后先运行
  `worktree merge inspect --worktree-id WT-ID`，让 controller 只读报告父 Plan
  是否相对 fork 基线漂移；无漂移时再由模型显式把 close summary/证据吸收到父
  Plan。ledger 永远是 `NON_AUTHORITY`，不能成为第二 Plan 权威。

## 确认判断

是否询问用户由模型负责，结合当前用户授权、项目规则、动作风险、影响面、
可逆性、现有证据和秘密/远端/生产/数据/破坏性边界判断。`action authorize`
和 `action lease` 是可选的 durable authority 记录机制，不是默认决策规则。
