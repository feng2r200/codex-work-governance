# Codex 工作流整体调研记录（2026-11-04）

## 本文件的使用方式（执行者必读）

本文件记录的是**截至 2026-11-04 的取证结论**，用于让执行者在动手前理解背景与约束，避免凭空假设。

**但现实优先于本记录。** 执行时若发现实际情况与本文记载不符：

1. **不得照搬本记录的结论继续执行。**
2. 以现场可复现的证据为准，重新判定。
3. 把差异与新证据追加到本文「差异与修订」一节，注明发现时间与复现方式。
4. 若差异足以改变方案方向，**停下来重新定方案**，而不是在旧方案上打补丁。

本记录的每条结论都标注了证据等级与复现命令。没有标注证据的内容一律按「未验证」对待。

**证据等级定义**：

| 等级 | 含义 |
|---|---|
| **确定性** | 二进制内嵌契约、源码、活体实验直接证明或证伪，无替代解释 |
| **强证据** | 大样本统计或多路交叉印证，存在但不太可能有替代解释 |
| **弱证据** | 单一来源或样本有限，方向可信但需复验 |
| **推测** | 尚无证据，仅为待验证假设 |

---

## 0. 调研起点

用户提出三个问题：

1. Token 消耗过大，怀疑与上下文压缩或多 Agent 配置有关。
2. 用 Pi 接手 `agent_buddy` 项目后推进更顺利，怀疑根 `AGENTS.md` 或 work-governance 需优化。
3. WorkVCS 的 Plan/Task/Todo/Knowledge 分层记录设计意图未落地。

调研覆盖范围：`~/.codex/config.toml`、根 `AGENTS.md`、work-governance 插件、WorkVCS、51 个 Codex 会话（2026-10-27 ~ 11-02）、24 个 Pi 会话、Codex 原生二进制。

---

## 1. 方法论：本次调研真正起作用的做法

这部分是后续要沉淀进 Plugin 的核心，排在结论之前。

### 1.1 每个「怀疑」都必须先被量化，然后多半会被证伪

用户最初的三个怀疑中，**与 Token 相关的两个都被数据证伪了**：

| 初始怀疑 | 实测占比 | 判定 |
|---|---|---|
| 多 Agent（SubAgent）是 Token 主因 | 0.03%（含 fork_turns 全额也仅 0.22%） | 证伪 |
| 截图/图片是主因 | 2.74% | 证伪 |
| WorkVCS 是主因 | 1.7% | 证伪 |

如果按最初的直觉动手（去掉多 Agent 能力），**会付出能力代价却几乎不省 Token**。

**真正的主因**是两个完全没被怀疑过的因素：轮次数 8 倍差 × 单轮上下文 3.84 倍差。

教训：**在没有量化之前，任何归因都不可信，包括自己的直觉和用户的直觉。**

### 1.2 「零记录」是决定性负面证据，不是数据缺失

本次调研多次靠「某个计数恰好为 0」锁定根因：

- `~/.codex/.work-governance/evidence/records/` 在 Oct 27–Nov 2 **零记录**
- `packets/`、`emitted/` 自 Oct 13 **恒空**
- 674 份 capture manifest 中 `knowledge` 非空的有 **0 份**
- 395 次压缩的生成式摘要 `message` **全部为空**
- 51 个会话中 `additionalContext` 出现 **0 次**
- `knowledge` 子命令被调用 **0 次**

一个本该被频繁写入的通道恒为零，说明它根本没有写入方，而不是写得少。

### 1.3 必须做正向对照，否则无法区分「坏了」和「没装」

最关键的一步：PreCompact 交接失效时，有两种解释——hook 代码写错了，或者没人调用它。

**正向对照实验**直接把 `stage-context` 手工跑通，证明 hook 侧实现完全正确、能正确产出 `hookSpecificOutput.additionalContext`。这一步排除了「代码写错」，把失败点唯一锁定为「没有写入方」。

同理，在验证 `UserPromptSubmit` 通道时，第一次实验得到 `UNKNOWN`（看似证明通道不可用），但追加的「hook 是否真的执行了」探针（`fired.log`）显示 **hook 根本没运行**。若没有这个探针，会得出完全错误的结论。

**原则：负面结果出现时，先证明实验装置本身是通的。**

### 1.4 一个结论站不住就必须整体重做方案，不能打补丁

本次调研中，上一轮方案的第一项在最后一刻被完全推翻：

- 旧方案：「让 `stage-context` 成为压缩前必经调用」
- 新证据：Codex 的 `pre-compact.command.output` schema 中 `additionalProperties: false`，**根本不接受 `additionalContext`**
- 结果：该项**整体作废重写**，改为 PreCompact 写 / UserPromptSubmit 读的双通道

如果当时只是「在旧方案上补一个 fallback」，产出的会是第二个死代码。

### 1.5 工具失效要早切换，不要重复撞墙

`write` 工具、heredoc、codemode base64、多行 `python3 -c` 在本项目中**连续 5 次**破坏 Python 缩进（`IndentationError`）。

**正确做法是在第 2 次失败时就切换通道**，改用 `jq` / `awk` / `sqlite3` / 单行命令。本次调研在这一点上做得不好，浪费了若干轮。

### 1.6 区分「注入成本」与「调用成本」

Skill catalog 被注入 ≠ Skill 被使用。工具 schema 被注入 ≠ 工具被调用。

本次最大的单笔浪费（626M tokens）正是「注入了但从未调用」的 54 个工具 schema。两个口径必须分开统计。

---

## 2. Token 消耗归因

### 2.1 总量（确定性，全量聚合）

口径：`event_msg.payload.type=="token_count"` → `.info.last_token_usage.*`，47,015 turns。

| 指标 | 数值 |
|---|---|
| input tokens | 8,974,441,336 |
| 其中 cached | 8,872,148,736（98.9%） |
| output tokens | 21,006,985 |
| reasoning tokens | 8,383,278 |
| **平均 input/turn** | **190,884** |
| model_context_window | 475,000 |
| plan_type | pro |

### 2.2 Codex vs Pi 对照（确定性）

| 指标 | Codex | Pi | 倍数 |
|---|---|---|---|
| 平均 input/turn | 190,884 | 49,690 | **3.84x** |
| 轮次总数 | 47,015 | 5,892 | **8.0x** |
| 压缩触发阈值 | 448K–450K | median 198,537 | — |
| 压缩摘要大小 | **0**（全空） | 18,727 B ≈ 4,681 tok | — |
| 压缩率 | 0.84% | 4.51% | — |

**综合解释**：Codex 总消耗 ≈ Pi 的 30 倍，由「轮次 8 倍 × 单轮 3.84 倍」构成。

### 2.3 工具输出分布（确定性）

全部工具输出：47,591 调用 / 260,541,068 B ≈ 65,135,267 tokens。

按调用形态二级归类（复现：见 §7 awk 脚本）：

| 类别 | 调用数 | 字节 | 占比 |
|---|---|---|---|
| `[exec_multi]`（shell 命令） | 28,910 | 227,675,577 | **87.39%** |
| `[unknown]` | 7,429 | 8,568,350 | 3.29% |
| `[write_stdin]` | 4,284 | 8,486,866 | 3.26% |
| `[view_image]` | **8** | 7,133,040 | 2.74% |
| `[js-other]` | 234 | 4,905,041 | 1.88% |
| `[web_search]` | 101 | 2,616,413 | 1.00% |
| `[apply_patch]` | 6,623 | 1,153,120 | 0.44% |

shell 命令内部按命令名归类：

| 命令 | 调用数 | 字节 | 占比 |
|---|---|---|---|
| `sed` | 3,252 | 39,473,139 | 15.15% |
| `rg` | 3,424 | 31,964,807 | 12.27% |
| `nl` | 615 | 11,337,481 | 4.35% |
| `cat` | 688 | 6,318,880 | 2.43% |
| `node` | 1,751 | 3,553,385 | 1.36% |

**关键观察**：`sed` + `rg` + `nl` + `cat` = **34.2%** 的工具输出字节，全部是**文件读取与搜索**。这说明大量 Token 花在反复读取同样的文件内容上——与 §3 的「压缩后重读 SKILL.md 515 次」现象同源。

`[view_image]` 仅 **8 次调用**就产生 7.1 MB（2.74%），单次平均 891 KB。虽非主因，但单次成本极高。

### 2.4 长尾结构（强证据）

47,591 条输出，中位数 **568 B**。top100 占 4.7%，top1000 占 19.3%，top5000 占 **61.2%**。

**含义**：优化不能只盯最大的几条，但也不必管绝大多数小输出。有效区间是「前 5000 条」。

### 2.5 每轮固定开销（确定性）

developer message 总计 **44,245 B ≈ 11,061 tokens/轮**：

| 组成 | 字节 |
|---|---|
| `skills_instructions` | 16,321 |
| `app-context` | 7,856 |
| `tools` | 2,298 |
| `recommended_plugins` | 811 |

加上 AGENTS.md 注入（根 10,030 B + 项目 11,628 B = 21,658 B ≈ 5,414 tokens），**每轮纯前缀约 16.5K tokens**。

---

## 3. 最大单笔浪费：未使用的工具 schema

### 3.1 事实（确定性）

`exec` 工具的 description 长 **76,214 B ≈ 19,000 tokens**，内部通告 62 个嵌套工具。

按 namespace 拆分：

| namespace | 工具数 | 字节 | ≈tokens |
|---|---|---|---|
| `mcp__codex_app` | 49 | 49,268 | 12,317 |
| `web` | 1 | 10,361 | 2,590 |
| `(core)` | 10 | 8,585 | 2,146 |
| `image_gen` | 1 | 2,519 | 630 |
| `clock` | 1 | 290 | 73 |

嵌套工具的**真实调用次数**：

| 工具 | 调用数 |
|---|---|
| `exec_command` | 29,122 |
| `write_stdin` | 4,287 |
| `apply_patch` | 379 |
| `web__run` | 104 |
| `clock__curr_time` | 44 |
| `mcp__codex_app__read_thread` | 14 |
| `view_image` | 8 |
| `mcp__codex_app__open_in_codex` | 1 |
| **其余 54 个** | **0** |

**54 个工具 / 53,268 B（约 13,317 tok/轮）× 47,015 轮 ≈ 626M tokens**，是 work-governance catalog 注入成本（178M）的 3.5 倍。

### 3.2 注入源（确定性）

`~/.codex/config.toml:123`：

```toml
[plugins."codex-app-tools@openai-bundled"]
enabled = true
```

插件定义：`~/.codex/plugins/cache/openai-bundled/codex-app-tools/26.1029.61003/.mcp.json`，注册 MCP server `codex_app`，暴露 49 个工具。

### 3.3 裁剪手段（确定性）

Codex 二进制的 `RawMcpServerConfig` 结构（30 字段）含以下工具级门控字段：

```
enabled_tools / disabled_tools / omit_tools_from / default_tools_approval_mode
```

`.mcp.json` 当前 `omit_tools_from: []`，未做任何裁剪。

**精确收益计算**（复现见 §7）：

```
codex_app 工具块总字节       48,714
保留 read_thread+open_in_codex  3,188
可裁剪          45,526 B ≈ 11,381 tokens/轮
```

按 47,015 轮计 ≈ **535M tokens**。

**注意**：此项与 WorkVCS 完全无关（见 §5.1），责任方是 `codex-app-tools@openai-bundled` 插件配置。

---

## 4. 压缩与上下文交接

### 4.1 Codex 原生压缩是「残缺保全」（确定性）

395 次压缩的统计：

| 指标 | 数值 |
|---|---|
| 生成式摘要 `message` 为空 | **395 / 395（100%）** |
| 平均 `retained_context` | 3,851 B |
| 平均 `replacement_history` | 312,337 B |
| `user_messages` 保留 0 条的次数 | **356 / 395** |
| `assistant_messages` 恰好保留 8 条 | **310 / 395**（硬上限） |

**含义**：压缩丢掉的恰恰是**用户原始指令与授权边界**，保留的是最近 8 条助手输出。这直接导致压缩后模型不知道原始目标，于是重读 SKILL.md（**515 次 / 7,966,787 B ≈ 1,991,696 tokens**），用户被迫手工重建交接 **3 次**。

### 4.2 PreCompact 交接通道是死代码（确定性）

work-governance 注册了 PreCompact hook，但：

- `packets/`、`emitted/` 自 Oct 13 **恒空**
- `hook_runtime.py:218 _context_output()`：`if packet is None: return b""`
- `stage-context` 子命令**零调用者**
- `observations.jsonl`：pre-compact 仅 **27** 次（占 3406 条的 6.8%），`elapsed_us` min 19 / median 25 / max 36，与「空快路径」一致

### 4.3 决定性发现：PreCompact 根本不接受 additionalContext

**证据来源**：Codex 原生二进制内嵌的 23 份具名 JSON Schema。

复现：

```bash
B=~/.volta/tools/image/packages/@openai/codex/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex
strings -a "$B" > /tmp/codexstr.txt
awk 'index($0,"pre-compact.command.output{"){f=1; sub(/^.*command\.output\{/,"{")} f{print; if($0 ~ /^\}/) exit}' /tmp/codexstr.txt
```

`pre-compact.command.output` 原文（`additionalProperties: false`）：

```json
{
  "additionalProperties": false,
  "properties": {
    "continue":       {"default": true,  "type": "boolean"},
    "stopReason":     {"default": null,  "type": "string"},
    "suppressOutput": {"default": false, "type": "boolean"},
    "systemMessage":  {"default": null,  "type": "string"}
  },
  "title": "pre-compact.command.output"
}
```

**没有 `hookSpecificOutput`，没有 `additionalContext`。** `post-compact.command.output` 字段完全相同。

支持 `hookSpecificOutput` 的事件只有 6 个（二进制中 `*HookSpecificOutputWire` 的完整集合）：

```
PreToolUse (5 字段，含 additionalContext)
PostToolUse (3 字段，含 additionalContext)
SessionStart (2 字段，含 additionalContext)
SubagentStart (2 字段，含 additionalContext)
UserPromptSubmit (2 字段，含 additionalContext)
PermissionRequest (2 字段，不含)
```

二进制中的显式守卫字符串：

```
$ignoring additionalContextLimit for  … hook in …
*: this event cannot emit additionalContext
```

即 PreCompact 写 `additionalContext` **不报错、被静默丢弃**。这解释了为何 51 个会话中该字段出现 0 次却无任何错误日志。

**此发现推翻了上一轮方案的第一项。**

### 4.4 UserPromptSubmit 通道实测可用（确定性，活体实验）

实验设置：隔离 `CODEX_HOME`、空工作目录、禁用工具、固定 magic string。

```bash
# hook 脚本
printf '%s' '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"CONTEXT NOTE: the passphrase is QUETZAL-7731."}}'

# hooks.json（注意顶层必须是 {"hooks":{...}}）
{"description":"pc","hooks":{"UserPromptSubmit":[{"hooks":[{"command":"/path/ups.sh","type":"command"}]}]}}

codex exec --dangerously-bypass-hook-trust --skip-git-repo-check \
  "Do not use any tools. What is the passphrase? If you do not know, reply exactly UNKNOWN."
```

结果：

```
hook: UserPromptSubmit
hook: UserPromptSubmit Completed
codex
QUETZAL-7731
```

会话记录中的注入形态：

```json
{"type":"message","role":"developer",
 "content":[{"type":"input_text","text":"CONTEXT NOTE: the passphrase is QUETZAL-7731."}],
 "content_item_kinds":["hooks.additional_context"],
 "content_item_metadata":[{"provenance":{"type":"harness","hook":true}}]}
```

**结论**：`UserPromptSubmit → additionalContext` 通道确认可用，以 `role=developer` 注入，带 `hooks.additional_context` 标记。

**实验严谨性记录**（方法论价值）：
- 第 1 次：模型用 `rg` 搜到了 hook 脚本本身从而「作弊」答对 → 该轮作废
- 第 2 次：空目录 + 禁工具复测得 `UNKNOWN` → 看似通道不可用
- 追加 `fired.log` 探针：发现 **hook 根本没执行**
- 第 3 次：定位到 hook 信任机制（见 §4.5），加 `--dangerously-bypass-hook-trust` 后成功

### 4.5 hook 需要 trusted_hash 才会运行（确定性）

未注册信任的 hook **静默不执行，无任何警告**。信任态存于 `config.toml`：

```toml
[hooks.state."/Users/ld/.codex/hooks.json:pre_compact:0:0"]
trusted_hash = "sha256:ddd28eece9b3ab3c4f07d61efd2140f029438b2cc59908503c71d977bbfc408a"
```

`trusted_hash` 绑定 hook **命令字符串**，而 work-governance 的命令内含 `--package-digest 4079c966…`。

**推论（强证据，未完全结案）**：插件内容变化 → digest 变 → 命令字符串变 → 哈希失配 → hook 静默失效。这与以下观察一致：

- pre-compact 仅来自 **3 个** distinct session_key，而 session-start 有 **50 个**
- 存在 2.8.0 / 2.9.0 两个插件缓存版本并行
- 活跃会话 r10 指向 `work-governance/2.8.0/skills`（该目录已不存在）

**此推论是 pre_compact 触发率仅 6.8% 的最可能解释，执行前应复验。**

### 4.6 PreCompact 能拿到 transcript_path（确定性）

`pre-compact.command.input` schema 的 required 字段：

```
cwd, hook_event_name, model, session_id, transcript_path, trigger, turn_id
```

`trigger` 枚举为 `manual | auto`。

**含义**：PreCompact hook 可自行读取完整 transcript 提取用户指令全集，**不依赖引擎摘要**（而引擎摘要恰好是空的）。

### 4.7 修正后的交接架构

```
PreCompact        : 只能"写"。读 transcript_path，提取 user 指令全集 +
      授权边界 + 当前目标 + 未完成项，落盘 packet
UserPromptSubmit  : 只能"读"。压缩后首条用户消息时注入 additionalContext
```

`additionalContextLimit` 是 `HookHandlerConfig::Command` 的 6 个字段之一，可在 `hooks.json` 显式设定，不必依赖默认值。

---

## 5. WorkVCS

### 5.1 不是 Token 问题（确定性证伪）

| 指标 | 数值 |
|---|---|
| 调用数 / 字节 | 882 / 4,376,926 B ≈ 1,094,231 tokens |
| 占全部工具输出 | **1.7%** |
| SKILL.md 读取 | 18,559 B × 23 次 = 426,857 B ≈ 106,714 tokens |
| help 类调用 | 88 次 / 16,974 B |
| **合计占总量** | **约 0.01%** |

**且 WorkVCS 不在任何 tool schema 中**：`grep -c workvcs` → `execd.txt`=0、`exectool.txt`=0。62 个嵌套工具中 0 个。100% 通过 `exec_command({cmd:"workvcs …"})` shell 字符串调用。

**结论：§3 的 626M schema 浪费与 WorkVCS 完全无关。WorkVCS 不做任何 Token 优化，它的问题纯粹是设计正确性。**

### 5.2 Knowledge 通道从未落地（确定性）

| 指标 | 数值 |
|---|---|
| capture manifest 总数 | 674 |
| 其中 `knowledge` 非空 | **0** |
| `knowledge` 子命令调用次数 | **0** |
| agent_buddy store 中 knowledge 实体 | 4（全部由 capture 路径外产生） |

`records=` 分布：1→632、2→114、3→56、4→15、5→3、6→7、0→5。

**根因（源码级，`crates/workvcs-core/src/history/capture.rs:489`）**：

```rust
if manifest.records.is_empty() && manifest.knowledge.is_empty() {
    return Err(capture_field_invalid(
 "$.records and $.knowledge",
        "at least one Record or Knowledge item",
        "both arrays are empty; standalone Evidence must use evidence create",
    ));
}
```

准入条件是 `&&`——**只要有一条 record 就放行，knowledge 永远可以为空**。没有任何机制要求或提示把累积的 finding 提升为 knowledge。

**补充确认**：全仓库 `rg "promot"` 的结果全部属于 `runtime/continuation.rs` 的会话轮换（CarrierPromotion），**与 finding→knowledge 的知识提升无关**。该提升路径在代码中不存在。

CLI 的 help 文本里**已经给出了正确范例**（`main.rs:94290-94303`），含 `knowledge` 项与 `validates` 关系，但没有任何强制或提示机制，因此 674 次实际使用中无一采纳。

### 5.3 语义严重倾斜（强证据）

record kind 分布（agent_buddy store，共 2480 条）：

| kind | 数量 |
|---|---|
| finding | **1864** |
| decision | 710 |
| attempt | 143 |
| handoff | 17 |
| question | 12 |
| risk | 2 |

实际命令使用（51 会话 2293 次调用）：capture 704、capture-validate 673、record 352、project 126、recall 105、runtime 101。**244 个 leaf 命令中仅约 30 个被触达。**

### 5.4 层级实为 relation 表承载，refs 字段是结构性死字段（确定性）

关系表分布：

| relation_type | 数量 |
|---|---|
| supersedes | 202 |
| derived_from | 38 |
| supports | 30 |
| contains | 29（plan→task 25 / goal→plan 4） |
| validates | 4 |
| references | 3 |
| verifies | 1 |
| invalidates | 1 |
| evidenced_by | 1 |

而 `plan_refs` / `task_refs` / `work_refs` / `subgoals` 四个字段**被代码强制要求为空数组**：

```rust
// crates/workvcs-core/src/history/goal.rs:670
fn require_empty_array(field: &str, value: &CanonicalValue) -> Result<()> {
    match value {
        CanonicalValue::Array(values) if values.is_empty() => Ok(()),
        CanonicalValue::Array(_) => Err(WorkVcsError::GoalInvalid(format!(
     "{field} is deferred and must be an empty array in Phase 3M"
        ))),
        ...
```

`plan.rs:768` 有同样的函数（措辞为 Phase 3J）。

**判定修正**：层级并非完全缺失（relation 表有 contains）。真正问题是这四个字段是**结构上被禁止写入的并行表示**，属于未完成的阶段性遗留，应删除。

**注意**：删除需同步改动 `goal.rs` / `plan.rs` 的构造与解析路径及对应测试（`goal_lifecycle_phase3o.rs`、`goal_phase3m.rs`、`plan_lifecycle_phase3p.rs`、`plan_phase3j.rs`），因为解析器目前**强制要求这些字段存在**（缺失会报 `missing task_refs`）。

### 5.5 supersedes 链极长（确定性）

agent_buddy store 的 supersedes 链深度分布：

```
深度 1: 202   深度 10: 47   深度 20: 23   深度 30: 11
深度 2: 105   深度 15: 33   深度 25: 16   深度 38: 1
```

**最长链 38 层。** 意味着同一条事实被反复 supersede 了 38 次，而非提升为一条稳定 knowledge。这与 §5.2 的 knowledge=0 互为印证：**缺少知识提升通道，导致认知只能以"不断覆盖 finding"的方式累积。**

### 5.6 capture-validate 冗余（确定性证伪）

错误码扫描：`admission_denied` 4、`invalid_manifest` 1。**证伪了「capture-validate 大量失败」的假设。**

源码确认：`validate_semantics` 在 `history/capture.rs:157` 定义，而 **`capture.rs:394` 的 capture 路径本身也调用同一校验**。capture 326 次 vs capture-validate 108 次（ratio 0.33）。

**判定：capture-validate 是成功但冗余的往返。**

### 5.7 人机工学不对称（强证据）

| 命令 | STORE | cwd | branch |
|---|---|---|---|
| `KnowledgeCommand` | 10 | **0** | 6 |
| `TaskCommand` | 9 | **0** | 5 |
| `PlanCommand` | 9 | **0** | 4 |
| `GoalCommand` | 6 | **0** | 4 |
| `StoreCommand` | 28 | **0** | 2 |
| `RecordCommand` | 36 个子命令中 29 个强制 `--branch` | — | — |
| `SearchCommand` | — | **7** | — |
| `ProjectCommand` | — | **4** | — |
| `Capture` | — | **1** | — |

help 求助信号：**16 种 help 调用 / 共 77 次**；畸形调用 `recall ---`、`gate ---`、`discover ---`、`workvcs --glob`。

**注**：上一轮曾建议「为 `knowledge` 子命令增加 `--cwd` 自解析」，后因 §5.2 的根因是准入规则而非 CLI 表面，**该建议已自我证伪撤回**。

### 5.8 规模

269 个 `.rs` / **306,480 行**；core 122,807；cli 109,178（**`main.rs` 单文件 95,601 行**）；version 1.7.0。
**37 个 `*Command` 枚举 / 244 leaf 命令。**

---

## 6. work-governance 插件

### 6.1 Skill 加载极度集中（确定性）

实际读取次数：

| Skill | 次数 |
|---|---|
| work-lifecycle | **239** |
| code-intelligence | **69** |
| workvcs | 24 |
| problem-discovery | 14 |
| independent-validation | 11 |
| subagent-governance | 9 |
| work-reporting | 8 |
| frontend-governance | 6 |
| git-change-governance | 4 |
| plan-governance / goal-discovery / continuation-governance | 各 2 |

work-lifecycle + code-intelligence = **79%**。

**零读取的 work-governance skill 为 4 个**：
`project-development-governance`、`project-truth-governance`、`project-archive-curation`、`resource-observation`

### 6.2 未触发原因（已查清）

**原因 A（强证据）：catalog 描述含「否定式自我排除」尾句。**

实测四条描述的尾句：

- `project-development-governance`：`Do not use for isolated edits or one-off investigations outside an enrolled project.`
- `project-archive-curation`：`Do not use for ordinary file backup or storage cleanup.`
- `resource-observation`：`Ordinary work does not require a separate resource audit.`
- `project-truth-governance`：（无否定尾句，但表述高度抽象）

**原因 B（确定性）：转派路径存在但同样带抑制语。**

`work-lifecycle/SKILL.md` 确实含转派（复现：`grep -n` 该文件）：

- `:208` → `project-development-governance`
- `:212` → `project-truth-governance`
- `:216` → `resource-observation`
- **`project-archive-curation` 完全没有被 work-lifecycle 引用**

且 `:216` 的转派句本身带抑制尾句：`Ordinary work needs no separate resource audit.`

**决定性反例**：`resource-observation` 的触发条件在 10-28 被精确命中两次——
- `users.txt:66`「目前的Token消耗分布是什么样子？」
- `users.txt:79`「从我的Token消耗可以看出，大部分消耗在SubAgent。」

两次都**完全符合**「assessing or recording meaningful consumption」，**却零加载**。

**判定：检测失效，不是 skill 无用。处置为「修检测，不删 skill」。**

### 6.3 catalog 注入成本

44 条目 / 15,170 B ≈ **3,792 tokens/轮**；17 个 work-governance skill 全在 catalog 内。按 47,015 轮计 ≈ 178M tokens——**仅为 §3 工具 schema 浪费（626M）的 28%**。

### 6.4 治理规则事后追加（弱证据）

`10-28 bc3014c`、`10-13 5f04d42`、`10-05 281df92` 三次提交显示治理规则是在问题暴露后追加的，而非预先设计。

### 6.5 规模

3994 行。`runtime/hook_runtime.py` 1091、`project-contract.md` 308、`work-lifecycle/SKILL.md` 261、`plan-governance/SKILL.md` 230、`problem-discovery/SKILL.md` 221、`project-development-governance/SKILL.md` 213、`continuation-governance/SKILL.md` 182。

---

## 7. 关键复现命令

### Codex 二进制 schema 提取

```bash
B=~/.volta/tools/image/packages/@openai/codex/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex
strings -a "$B" > /tmp/codexstr.txt     # 626,005 行

# 列出全部 23 份 schema
grep -o '"title": "[a-z-]*\.command\.[a-z]*"' /tmp/codexstr.txt | sort -u

# 提取任一份（注意 grep -x 无效，字符串被拼接在大 blob 中）
awk 'index($0,"user-prompt-submit.command.output{"){f=1; sub(/^.*command\.output\{/,"{")} f{print; if($0 ~ /^\}/) exit}' /tmp/codexstr.txt
```

### Token 聚合口径

```bash
# Codex
jq 'select(.type=="event_msg" and .payload.type=="token_count")
    | .payload.info.last_token_usage
    | [.input_tokens,.cached_input_tokens,.output_tokens,.reasoning_output_tokens]'

# Codex 压缩
jq 'select(.type=="compacted")
    | .payload | {message,retained_context,replacement_history_metadata,window_number}'

# Pi
jq 'select(.type=="message") | .message.usage | {input,cacheRead,output,reasoning}'
jq 'select(.type=="compaction") | {tokensBefore,summary,fromHook}'
```

### 工具输出二级归类

```bash
cd /tmp/wgmine && awk -F'\t' '
/^CALL/ { cur=$0; next }
/^OUT/  { if(cur==""){next} b=$2+0; c=cur; key="";
  if (index(c,"view_image")) key="[view_image]";
  else if (index(c,"apply_patch")||index(c,"Begin Patch")) key="[apply_patch]";
  else if (index(c,"write_stdin")) key="[write_stdin]";
  else if (index(c,"web__run")) key="[web_search]";
  else if (index(c,"exec_command")) key="[exec_multi]";
  else if (index(c,"tools.")) key="[js-other]"; else key="[unknown]";
  agg[key]+=b; cnt[key]++; tot+=b; cur=""; next }
END{ for(k in agg) printf "%-16s %8d %14d %7.2f%%\n",k,cnt[k],agg[k],100*agg[k]/tot | "sort -k3 -rn" }
' allpairs.tsv
```

### codex_app schema 裁剪收益

```bash
cd /tmp/wgmine && python3 -c "
import re
d=open('execd.txt',encoding='utf-8',errors='replace').read()
keep={'read_thread','open_in_codex'}
pos=[(m.start(),m.group().replace('mcp__codex_app__','')) for m in re.finditer(r'mcp__codex_app__[a-z_]+',d)]
seen=[]
for p,n in pos:
    if not seen or seen[-1][1]!=n: seen.append((p,n))
tot=kept=0
for i,(p,n) in enumerate(seen):
    end=seen[i+1][0] if i+1<len(seen) else pos[-1][0]+len(n)+20
    tot+=end-p
    if n in keep: kept+=end-p
print('total',tot,'kept',kept,'removable',tot-kept,'tokens',(tot-kept)//4)
"
```

### WorkVCS store 查询

```bash
cd ~/.codex/workvcs/stores/projects
DB="git-7611aa64d98159d9aef56d2bbd0f701b2294d774d854279a2845e263df4cccce.sqlite"  # agent_buddy

sqlite3 "$DB" "SELECT entity_kind,COUNT(*) FROM entity GROUP BY entity_kind ORDER BY 2 DESC;"
sqlite3 "$DB" "SELECT relation_type,COUNT(*) FROM relation GROUP BY relation_type ORDER BY 2 DESC;"

# supersedes 链深度（注意 entity_version 外键是 entity_id，不是 object_id）
sqlite3 "$DB" "WITH RECURSIVE ch(root,node,depth) AS (
  SELECT source_object_id,target_object_id,1 FROM relation WHERE relation_type='supersedes'
  UNION ALL
  SELECT ch.root,r.target_object_id,ch.depth+1 FROM relation r
    JOIN ch ON r.source_object_id=ch.node
   WHERE r.relation_type='supersedes' AND ch.depth<50)
 SELECT depth,COUNT(*) FROM ch GROUP BY depth ORDER BY depth;"
```

### hook 端到端验证

```bash
# 隔离环境（务必不要污染 ~/.codex）
export CODEX_HOME=/tmp/ht/ch && mkdir -p $CODEX_HOME && cp ~/.codex/auth.json $CODEX_HOME/
cat > $CODEX_HOME/config.toml <<'TOML'
model = "gpt-5.6-sol"
approval_policy = "never"
sandbox_mode = "read-only"
TOML
# 顶层结构必须是 {"hooks":{...}}，直接写 {"UserPromptSubmit":[...]} 会报 unknown field
cat > $CODEX_HOME/hooks.json <<'JSON'
{"description":"pc","hooks":{"UserPromptSubmit":[{"hooks":[{"command":"/tmp/ht/ups.sh","type":"command"}]}]}}
JSON
# 必须加 --dangerously-bypass-hook-trust，否则 hook 静默不执行
codex exec --dangerously-bypass-hook-trust --skip-git-repo-check "..."
```

---

## 8. 已证伪清单（防止重走弯路）

| # | 被证伪的假设 | 证据 | 等级 |
|---|---|---|---|
| 1 | WorkVCS 是 Token 主因 | 1.7% | 确定性 |
| 2 | 截图/图片是主因 | 2.74%（仅 8 次调用） | 确定性 |
| 3 | ~~多 Agent 是主因~~ **此条作废，反转为成立** | 0.03% 是委派工具回执字节数，口径错误；按会话计费为 **72.8%**，见 §9 与案例 E | 已推翻 |
| 4 | capture-validate 大量失败 | 错误码近乎为零 | 确定性 |
| 5 | WorkVCS 占用 tool schema | 62 个嵌套工具中 0 个 | 确定性 |
| 6 | PreCompact 可注入 additionalContext | schema `additionalProperties:false` | 确定性 |
| 7 | 零读取 skill 无用应删除 | 10-28 两次精确命中却零加载 | 确定性 |
| 8 | WorkVCS 层级完全缺失 | relation 表有 contains 29 条 | 确定性 |
| 9 | 建议给 knowledge 加 `--cwd`（自我证伪） | 根因是准入规则非 CLI 表面 | 确定性 |
| 10 | hook 失效是因为代码写错 | 正向对照实验跑通 | 确定性 |
| 11 | `output/` 目录失控是 Token 主因 | 全部 `output/` 路径 28 calls / 62,356 B / **0.024%**；`harness-recovery` **0 calls** | 确定性 |
| 12 | 「在错误路径上越走越远」是主因 | 76 条唯一用户消息中无事后纪偏；真因是子代理的约束蒸发 | 强证据 |
| 13 | 压缩丢弃用户意图（主会话） | 主会话 10-31 压缩保留 8 条 user 消息；356 次为 0 均属子代理会话 | 确定性 |

---

## 9. 差异与修订

> 执行时发现与本记录不符的，追加到这里。格式：日期 / 差异描述 / 复现方式 / 对方案的影响。

### 2026-11-04 — §4.5 的 trusted_hash 推论被证伪

**原记载**：pre_compact 触发率仅 6.8%，强证据推论为 `trusted_hash` 因 `--package-digest`
变化而失配导致 hook 静默不执行。

**实测结果**：**该推论错误。hook 触发率实为约 100%。**

在 hook 观测窗口（首次 pre-compact 落盘 2026-10-29T04:59:50Z 起）内：

| 指标 | 数值 |
| --- | --- |
| 实际 compaction 事件 | 27 |
| pre-compact hook 触发 | 28 |

且 2026-11-04 11:51 仍有新的 pre-compact 触发，`packets/` 下存在当时的 `.lock` 文件。

**原 6.8% 是口径错误**：该比例由 `28 / 3406` 得出，而 3406 条观测中 3324 条是
PostToolUse。PostToolUse 每次工具调用触发，PreCompact 仅在压缩时触发，**两者分母不可比**。
正确分母是真实压缩次数，得出约 100%。

「pre-compact 仅 3 个 distinct session_key」同样不构成异常：实为 4 个，而窗口内
压缩集中在 6 个会话，其中单个会话独占 25 次，属压缩分布不均而非 hook 选择性失效。

**复现**：

```bash
S=~/.local/state/work-governance-hook/v1/observations.jsonl
# 各 handler 的首末时间与计数
for h in post-tool-use pre-compact session-start; do
  F=$(jq -r --arg h "$h" 'select(.handler==$h)|.observed_at_us' $S | sort -n | head -1)
  L=$(jq -r --arg h "$h" 'select(.handler==$h)|.observed_at_us' $S | sort -n | tail -1)
  N=$(jq -r --arg h "$h" 'select(.handler==$h)|.handler' $S | wc -l)
  printf "%-16s n=%-6s first=%s last=%s\n" "$h" "$N" \
    "$(date -r $((F/1000000)) '+%F %H:%M')" "$(date -r $((L/1000000)) '+%F %H:%M')"
done

# 同一窗口内的真实压缩次数（注意用 UTC 比较）
cd ~/.codex/sessions && find 2026/10 2026/11 -name '*.jsonl' -exec cat {} + \
  | jq -r 'select(.type=="compacted")|.timestamp' \
  | awk '$0>="2026-10-29T04:59:00Z"' | wc -l
```

**对方案的影响：结论方向不变，根因更收敛。**

PreCompact 交接失效的唯一原因是 §4.3 的确定性发现——PreCompact 的 output schema
不接受 `additionalContext`。hook 已执行且执行成功，但其意图输出被引擎静默丢弃。
这**加强**了第 3 项的必要性：问题不在触发，而在通道选错，PreCompact 写 packet /
UserPromptSubmit 读注入是唯一正确分工。

方案 A（发布流程加显式重新信任）**保留**，但性质由「修复措施」降级为「预防措施」——
信任机制确实存在且会静默失败（§4.5 的机制本身仍是确定性的），只是本次未触发该路径。

**方法论教训（已反映到 causal-attribution 的 Measure Before Attributing 一节）**：
比率必须用同一事件总体作分母。把两个触发频率量级不同的事件放进同一个分母，
会制造出完全虚假的异常。

### 2026-11-04 — §3 的 626M schema 浪费已被上游修复，第 1 项作废

**原记载**：`exec` 工具 description 76,214 B，内部通告 62 个嵌套工具，其中 54 个
零调用；`mcp__codex_app__*` 49 个 schema 共 48,714 B。按此估算累计浪费 ≈ 626M tokens，
并得出「第 1 项：`enabled_tools` 白名单，约省 535M」。

**实测结果：该浪费已不存在。Codex 现已延迟加载（defer）嵌套工具。**

按会话逐日比对 `exec` description：

| 日期 | `exec` description | 内含 `codex_app` |
| --- | --- | --- |
| 2026-10-27 → 10-29 | 数万 B | 是（最多 4158 行） |
| 2026-10-31 起至 11-02 | **26,352 B** | **零** |

当前 description 明文写着：

> Some deferred nested tools may be omitted from this description. They are
> still available on the global `tools` object and listed in `ALL_TOOLS`.
> To find one, filter `ALL_TOOLS` by `name` and `description`.

二进制中存在对应的 feature flag：`tool_search`、`tool_search_always_defer_mcp_tools`、
`deferred_tool_world_state`、`code_mode_tool_search`。即工具按需检索而非全量注入。

另外，`codex-app-tools` 的 `.mcp.json` 中 `codex_app` 本身已是 `"enabled": false`；
且该文件位于 Plugin 缓存路径，按项目约束不得依赖。

**复现**：

```bash
cd ~/.codex/sessions
for f in $(find 2026/10 2026/11 -name '*.jsonl' | sort); do
  D=$(jq -r '[..|objects|select(.name=="exec" and (.description|type=="string"))
       |.description]|max_by(length)' "$f" 2>/dev/null)
  [ -n "$D" ] && [ "$D" != "null" ] && printf "%-20s len=%-7s codex_app=%s\n" \
    "$(basename $f|cut -c9-24)" "$(printf '%s' "$D"|wc -c)" \
    "$(printf '%s' "$D"|grep -c codex_app)"
done
```

**对方案的影响：第 1 项整项作废。**
原本排序最高、收益最大的一项已由上游解决，不需要任何本地配置改动。
若强行写入 `enabled_tools` 白名单，只会在已经正确的行为上叠加冗余配置。

### 2026-11-04 — §4.1 的「摘要全空」是读数错误，第 2 项前提动摇

**原记载**：395 次压缩的生成式摘要 `message` 全部为空（0.0%），因此判定 Codex
原生压缩是「残缺保全」。

**实测结果：`message` 确实为空，但摘要并未丢失——它以加密形式存在。**

`replacement_history` 中每次压缩都含一个 `type=="compaction"` 项，其字段为
`{encrypted_content, id, internal_chat_message_metadata_passthrough, type}`。

| 日期 | 压缩次数 | 带 compaction 项 | 平均 `encrypted_content` |
| --- | --- | --- | --- |
| 2026-10-28 | 326 | 326 | 51,257 B |
| 2026-10-29 | 44 | 44 | 42,184 B |
| 2026-10-31 | 1 | 1 | 19,256 B |

覆盖率 100%。摘要存在于服务端加密载荷（配合 `compaction_response_id`、
`remote_compaction_v2` flag），客户端明文 `message` 空属正常设计，不是缺失。

**复现**：

```bash
cd ~/.codex/sessions
cat 2026/10/31/*.jsonl | jq -r 'select(.type=="compacted")
  |.payload.replacement_history[]|select(.type=="compaction")|keys|@csv'
```

**对方案的影响：第 2 项（压缩阈值 450K → 200K）失去原有论据，暂停。**
原论据是「Codex 压缩保全残缺，因此应少装多压」。既然保全并不残缺，该推论不再成立。
降阈值反而会提高压缩频率，在每次压缩都有固定开销的前提下可能适得其反。
若仍要调整，正确配置键为 `model_auto_compact_token_limit`（配合
`model_auto_compact_token_limit_scope`、`model_post_turn_compact_threshold_percent`），
但必须先用实测建立新论据。

### 2026-11-04 — §2 的 Token 归因需重测

上述两项证明平台已在调研期间发生结构性变化。平均 input/turn 实测：

| 日期 | turns | 平均 input |
| --- | --- | --- |
| 2026-10-28 | 37,589 | 188,384 |
| 2026-10-29 | 4,891 | 174,090 |
| 2026-11-02 | 350 | 224,362 |

11-02 样本量太小（350 turns）且工作负载不同，不足以评估 defer 的净效应。
§2 的结论（轮次 8 倍 × 单轮上下文 3.84 倍；`exec` 占工具输出 99.46%；
文件读取与搜索类 ≈ 34.2%）仍属历史观测，但**不得再作为当前归因使用**，
需在 defer 生效后的负载上重新采样。

---

### 2026-11-04 — 真因定位：子代理会话占 72.8% 计费（确定性）

前面所有归因都在单个会话内部找原因。按会话归属重新聚合后方向变了。
划分口径：会话内真实 `role=="user"` 消息 ≥ 5 条为主会话，其余为子代理会话。

| 类别 | turns | 压缩次数 | 计费 Token | 占比 |
| --- | --- | --- | --- | --- |
| 主会话 | 13,543 | 40 | 33,691,464 | 27.2% |
| 子代理会话 | 33,541 | 356 | 90,187,441 | **72.8%** |

单会话极端值：`10-28T23-37` 4,977 turns / 41 次压缩 / 10,331,849；
`10-29T00-13` 4,225 / 39 / 9,748,615；`10-28T21-14` 1,879 / 28 / 7,226,293。

三重放大机制（均有直接证据）：

1. **全量历史分叉**——151 次 spawn 中 `fork_turns="all"` 105 次、省略（默认即
   `all`）32 次，合计 **137/151（90.7%）携带全量父历史**；`none` 仅 14 次。
   子代理首轮（尚未开工）input 中位数 **149,540**、均值 196,568、最大 404,169。
2. **压缩时无用户意图可保留**——子代理不接收用户消息，故 356 次子代理压缩
   `retained_context.user_messages` 全为 0 条。对照主会话：10-31 那次压缩完整
   保留 8 条 user 消息（含「停在方案确认门」等关键约束）。父历史里的用户意图
   在子代理的第一次压缩后永久消失。
3. **孙代理递归**——跑了 4,977 轮的那个子代理自身文本中 `spawn_agent` 出现
   378 次；系统提示明写「Child agents can also spawn their own sub-agents」
   与「4 available concurrency slots」。

这解释了「Token 大但没进展」：不是走错路，是**约束蒸发**。子代理拿一份静态
任务描述出生，第一次压缩后连父历史也丢，然后在数千轮里自循环，用户既看不到
它也无法中途纠偏。主会话压缩完全正常，所以异常从未出现在可观测的位置。

由此修正两个旧结论：

- **「多 Agent 只占 0.03%」作废**——那是委派工具自身回执的字节数，不是被派发
  工作的成本。已立为 AGENTS.md 案例 E / R9。
- **「user_messages 356/395 次为 0」不是压缩缺陷**——该读数成立，但成因是这 356
  次均发生在本就没有 user 消息的子代理会话里。

**复现**：按会话遍历，以 `select((.payload.type//.type)=="message" and
(.payload.role//.role)=="user")` 计数划分主/子，再聚合
`.payload.info.last_token_usage` 的 `(input-cached)+output`。

### 2026-11-04 — 已关闭多 Agent 能力（已执行）

关闭前做了四项验证，没有按命名推断直接改：

1. **配置键权威性**——二进制中 `[agents]` 结构体仅 6 个字段
   （`max_concurrent_threads_per_session`、`max_depth`、`default_subagent_model`、
   `default_subagent_reasoning_effort`、`job_max_runtime_seconds`、
   `interrupt_message`），**字面上找不到 `enabled`**，故不能假定已有的
   `enabled = true` 有效。
2. **类型错误探针 + 同表控制组**——先测得未知键被静默忽略、已知键写错类型
   会报 `invalid data`。首次用 `[features]` 下的伪造键做控制组，得到「伪造键也被
   接受」而判定探针失效；将控制组移回 `[agents]` 同表后结论清晰：
   `[agents].bogus_xyz` 被 **拒绝**（`deny_unknown_fields`）而 `[agents].enabled`
   被接受且按 bool 校验 → `enabled` 是真字段。`[features]` 为开放映射，不可作门。
   （此次失误已立为 R10。）
3. **行为验证 + 正向对照**——隔离 `CODEX_HOME`、空工作目录、「禁止使用任何工具」
   提示。`enabled=false` 侧会话文件内六个多代理工具名 **0 次**、
   `"multi_agent_mode":{}` 为空；`enabled=true` 侧则 `spawn_agent`、`followup_task`、
   `wait_agent`、`send_message`、`list_agents` 均各现 1 次，
   `"multi_agent_mode":{"mode":"explicitRequestOnly",...}`。正向对照证明装置有效。
4. **收益口径**——多代理工具 schema 5,245 B；同一提示下首轮 input
   13,801（true）vs 12,273（false）= **每轮约 1,528 tokens**。主收益不在 schema，
   而在消除 137 次全量历史分叉与 33,541 轮子代理执行。

**变更**：`~/.codex/config.toml` 的 `[agents].enabled` 置 `false`，并在原处写入证据
与回滚注释。备份：`~/.codex/config.toml.bak-20261104-agents`。回滚：置回 `true`。

**关闭后复验**：真实 `CODEX_HOME` 下 `codex doctor` 配置 `✓ loaded`；新会话
`grep` 六个多代理工具名 0 命中、`"multi_agent_mode":{}` 为空。

**悬空引用排查**：根 `AGENTS.md`、项目 `AGENTS.md`、`config.toml` 均无主动委派
指令，也无 `worker_deep` 等角色自定义（角色来自内置）。`work-lifecycle` 对
`subagent-governance` 的转派带条件（「before multi-agent delegation」），自门控，
无需改动；该 skill 历史加载仅 9 次。故关闭后无悬空引用。

---

## 10. 当前已知未决项

| 项 | 状态 |
| --- | --- |
| pre_compact 触发率 | **已结案（2026-11-04）**：实为约 100%，原 6.8% 系分母口径错误，见 §9 |
| `additionalContextLimit` 默认值 | 未取得；但该字段可显式设定，不阻塞方案 |
| `systemMessage` 是否进入模型上下文 | 未验证；因 `additionalContext` 通道已可用，不再需要 |
| Pi 侧 WorkVCS 接入 | 用户明确暂不纳入范围 |
