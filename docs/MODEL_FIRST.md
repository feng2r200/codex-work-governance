# 模型优先读这个

这页是面向模型的短入口。完整参数以 `docs/CLI_REFERENCE.md` 和
`workctl help <workflow>` 为准。

## 快速路径

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
- 查旧 Plan 时，用 `plan history list|show`。这是宽松只读读取，不用旧历史
  格式约束当前 active schema。
- active Plan 只有插件当前声明的 schema-v5 可继续写。遇到 V3/V4 或任何
  非当前 schema 的 active Plan 时，只做只读摘要，然后用
  `migrate apply --expected-contract-revision <revision>` 归档旧 Plan 并重建
  schema-v5 contract；不要做状态适配、旧 task 状态迁移或
  `plan contract upgrade`。
- 判断高影响动作前，可用 `risk inspect --action-kind KIND --target-ref REF`
  获取风险事实。controller 不替模型决定是否必须向用户确认。
- 子 worktree 执行只记录
  `worktree begin|record|close`。这些 ledger 永远是 `NON_AUTHORITY`，父 Plan
  只吸收 close summary 和证据。

## 确认判断

是否询问用户由模型负责，结合当前用户授权、项目规则、动作风险、影响面、
可逆性、现有证据和秘密/远端/生产/数据/破坏性边界判断。`action authorize`
和 `action lease` 是可选的 durable authority 记录机制，不是默认决策规则。
