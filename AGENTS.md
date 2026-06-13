# AGENTS.md — AutoMisc

> **本文件 ≤ 200 行 · 治理变更 v3.0 · 2026-06-13**（per Owner: 把第一阶段内容全删）

## 0. 启动必读

AI Agent session 启动**按序读** 4 文件（其他不读）：

1. `AGENTS.md`（本文件，治理）
2. `STRUCTURE.md`（项目结构 + 模块作用，**取代已删 Architecture.md**）
3. `upgrade.md`（当前迭代入口）+ `upgrade/<id>.md`（当前任务详细）
4. （可选）`fix.md` + `prd.md`（🟡 frozen 历史 reference）

> **关键自检**：每次写代码前内部回答"对应 `upgrade.md` 哪行迭代？对应 `STRUCTURE.md` 哪节？"，答不出停手。

## 1. 4 铁律（不可绕过）

| 铁律 | 核心 |
|---|---|
| **1 · 文档先行** | 改动必须对应 `upgrade.md` 现有迭代；找不到 → 新需求，走铁律 2 |
| **2 · 新需求先文档** | 先 `STRUCTURE.md`（如需）+ `upgrade.md`（必有）+ Owner 自审 → 才能写代码 |
| **3 · 任务有状态** | `upgrade.md` 每行有 ⏳🔄✅⚠️❌ 状态；代码 + 文档**同 commit** |
| **4 · 未验证 = 未完成** | ① 合 main ② 单测全绿 ③ GUI 改跑集成 ④ 真实样本 smoke ⑤ Owner 自审 ⑥ 文档同步 |

> 第 4 条"完成"**不追求 flag 匹配**——automisc 是半自动化辅助工具，验收是"工具调用成功 + journal 关键可疑点命中"。

## 2. 衍生规则

- **2.1 粒度**：单 PR ≤ 400 行；不跨任务 ID；GUI 改 / Core 改分离
- **2.2 单 Owner**：Owner 自审 = Reviewer；main 唯一长期分支
- **2.3 macOS only**：所有 GUI 在 macOS 验证；不引入跨平台 hack；subprocess 走 macOS 标准 PATH
- **2.4 单 Owner Git 全权**（v0.1.1 治理）：
  - AI Agent **全权**执行 `git add/commit/branch/checkout/merge --no-ff/rebase/cherry-pick/fetch/log/diff`
  - AI Agent **必须询问 Owner** 后执行 `git push` / `gh pr merge` / 删临时分支（per §4 询问卡模板）

## 3. 违规 & 升级

| 等级 | 处理 |
|---|---|
| L1 轻微 | 补文档 / 改 PR 标题 / 拆任务 |
| L2 中度 | 关 PR 走铁律 2 重立 / 任务状态回退 |
| L3 严重 | 撤 PR + Owner 暂停认领新任务一周 / 撤 Owner 资格 |

## 4. 紧急通道（仅跳过铁律 2，1/3/4 永远不跳）

1. macOS 紧急修复（PySide6 兼容）：24h 内补铁律 2
2. CI 全红 hotfix：文档同 PR 跟上
3. Owner 现场特批：PR 描述写明原因 + 授权人

**3 类高风险远端操作询问卡**（每次执行前必走，Owner 回复 Y 后立即执行；n 跳过；修改后按指示）：

```
===== REMOTE OPERATION REQUEST =====
操作:  <git push | gh pr merge | 删临时分支>
仓库:  https://github.com/f4cknet/automisc.git
理由:  <实施完成 + 6 关验收摘要>
预期结果: <main 推进到新 commit / 远端分支删除>
不可逆性: 🔴 高（merge 错只能 Revert；删分支只能 reflog / GitHub support 恢复）
请确认: [Y/n/修改后]
==================================
```

## 5. AI Agent 特别条款

| ❌ 禁止 | ✅ 允许 |
|---|---|
| 主动修改 `upgrade.md` / `STRUCTURE.md` 之外的文件 | 对未识别需求做"需求澄清"提问（不实施先问）|
| 跳过 `upgrade.md` 直接写代码 | 建议"这看起来是新需求，走铁律 2" |
| commit / PR 描述漏迭代 ID | 引用 `upgrade.md` 迭代行 |
| 推测 / 编造路径 / 函数名 / 任务 ID | 引用 `STRUCTURE.md §2-§5` 速查 |
| 引入 LLM / 云端 / 在线编排（违反完全离线约束）| 治理变更通过后实施 |
| **`git push` / `gh pr merge` / 删临时分支**（per §2.4）| 打询问卡等 Owner 签字 |

## 6. 文档引用速查

| 想做什么 | 查 |
|---|---|
| 项目结构 + 模块作用 | `STRUCTURE.md` |
| 当前迭代 | `upgrade.md` 索引 + `upgrade/<id>.md` 详细 |
| 修复记录 | `fix.md` 索引 + `fix_<bug_name>.md` 详细 |
| 历史需求 | `prd.md`（🟡 frozen，仅参考）|
| 治理 / 铁律 / Git 流程 | `AGENTS.md`（本文件）|

## 7. 治理变更流程

1. Owner 起草变更提案
2. PR 描述写明"**治理变更**" + 原因
3. Owner 自审（**单 Owner 项目** per §2.2 跳过"其他维护者 Review"）
4. 合并后立即通知所有 Owner
5. 变更记录保留在本文档 §8 变更日志

## 8. 变更日志（保留最近 4 条）

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-13 23:01 | **3.0** | **文档体系 v3.0**：`AGENTS.md` 压到 ≤ 200 行（删 §9 任务快照 / §3-§4 简化 / 变更日志砍到 4 条）；`prd.md` frozen + 跳到 STRUCTURE.md；新增 `STRUCTURE.md` 186 行取代已删 Architecture.md。**净压缩 60% 行数**（1903 → 1160 → ≈ 800）。 |
| 2026-06-13 22:53 | **2.0** | **文档体系 v2.0**：删 `Architecture.md`（942 行，架构已落地到代码）；`prd.md` 标 🟡 frozen；新建 `STRUCTURE.md` 186 行（项目目录 + 模块作用 + 链速查）。净 -743 行。 |
| 2026-06-13 22:44 | **1.20** | **§2.4 简化 v3**（v0.1.1 治理）：AI Agent 全权 git（含 push/merge），3 类高风险操作必询问 Owner；批量授权不豁免询问。 |
| 2026-06-13 14:00 | **1.8** | **v0.1.0b-cleanup（PR0）**：合并两套任务体系为 `v0.1.0b-*`；重排 P0~P9。 |

> 末次归档：2026-06-13（v1.0~v1.19 已归档到 `docs/changelog/AGENTS.md_archived.md`）。
