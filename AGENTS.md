# AGENTS.md — AutoMisc

> **本文件 ≤ 200 行 · 治理变更 v3.3 · 2026-06-27**（per Owner: Windows only）

## 0. 启动必读

AI Agent session 启动**按序读** 4 文件（其他不读）：

1. `AGENTS.md`（本文件，治理）
2. `STRUCTURE.md`（项目结构 + 模块作用，**取代已删 Architecture.md**）
3. `upgrade.md`（当前迭代入口）+ `upgrade/<id>.md`（当前任务详细）
4. （可选）`fix.md` + `prd.md`（🟡 frozen 历史 reference）

> **关键自检**: 每次写代码前内部回答 "对应 `upgrade.md` 哪行迭代？对应 `STRUCTURE.md` 哪节？", 答不出停手.
>
> **GUI 工具栏来源**: 见 `STRUCTURE.md §3.5` — GUI 工具有两种后端来源: `tools/` adapter (调外部 CLI) vs `core/decoders/` decoder (纯计算). Owner 找 cipher 解密工具找不到 `tools/cipher/` 时, 先查 §3.5.

## 1. 7 铁律（不可绕过）

| 铁律 | 核心 |
|---|---|
| **1 · 文档先行** | 改动必须对应 `upgrade.md` 现有迭代；找不到 → 新需求，走铁律 2 |
| **2 · 新需求先文档** | 先 `STRUCTURE.md`（如需）+ `upgrade.md`（必有）+ Owner 自审 → 才能写代码 |
| **3 · 任务有状态** | `upgrade.md` 每行有 ⏳🔄✅⚠️❌ 状态；代码 + 文档**同 commit** |
| **4 · 未验证 = 未完成** | ① 合 main ② 单测全绿 ③ GUI 改跑集成 ④ 真实样本 smoke ⑤ Owner 自审 ⑥ 文档同步 |
| **5 · 训练驱动迭代** | 用真实 CTF 赛题喂 automisc；失败 → AI + ctf-misc/ctf-forensics 兜底解题 → 沉淀 `upgrade/v0.5-train-NNN-*.md`。详见下文 §5 专章。 |
| **6 · 架构优先** (per §5.2) | 单题打补丁陷阱: 任何针对单题的优化, 必须回答"能否泛化到同类题"。能泛化 (≥ 3 道同类命中) → 走架构层升级;只救这一道 → 写训练日志, 不动代码 |
| **7 · auto_run = 纯探测不抢下一步** (2026-06-21 18:57 Owner 拍板) | 整个 `automisc-gui` 的 auto_run (`find_suspicious_from_<type>`) 不论拖入图片/zip/rar/其他文件，铁律是**分析并发现尽可能多的可疑点进入"可疑点列表"**。由做题人 (Owner) 根据这些可疑点决定下一步用什么工具。<br/>**不**触发下一步工具 (chain / 操作 / extract) — SP 写到 journal 是建议，Owner 决策。<br/>**不**雕不修不爆 — auto_run 路径**禁止**任何写文件/触发 chain/调用操作类 adapter 的逻辑。<br/>反面 (2026-06-21 18:41 实战教训): v0.5-lsb-bytes-auto-run (`2025a51` + `a6fa83e`) 把 `lsb_bytes_extract` (操作类, 写 12 个 .bin) 接进 `FIND_SUSPICIOUS_PICTURE_TOOLS`, 违反本铁律, **已 revert (`d47c7c6` + `f239497`)**。正确路径: lsb_bytes_extract 只走 CLI (`automisc chain --chain lsb-bytes`) + GUI Run→Chain 弹 dialog (per v0.5-lsb-bytes-gui `c898a46`)。 |

> 第 4 条"完成"**不追求 flag 匹配**——automisc 是半自动化辅助工具，验收是"工具调用成功 + journal 关键可疑点命中"。
>
> 第 5 条是项目**主引擎**——automisc 的能力边界由"实战题目失败 → 架构反哺"滚动推进，不是空想设计。

## 2. 衍生规则

- **2.1 粒度**：单 PR ≤ 400 行；不跨任务 ID；GUI 改 / Core 改分离
- **2.2 单 Owner**：Owner 自审 = Reviewer；main 唯一长期分支
- **2.3 Windows only**（v0.5-windows-only 治理变更 v3.3 · 2026-06-27）：GUI / Core 仅在 **Windows** 平台验证；subprocess 走 `tools/paths.py:resolve_tool_binary`（PATH 优先 → `extend-tools/bin/win-x64/` fallback，per [`upgrade/v0.5-windows-only.md`](upgrade/v0.5-windows-only.md)）；GUI 菜单 `✓/✗` marker 检查 binary 可执行；Win 优先 extend-tools/ 装 .exe binary；macOS / Linux **不在范围**（v0.5+ 不评估）
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

1. Windows 紧急修复（PySide6 兼容）：24h 内补铁律 2
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

## 5. 训练驱动迭代（项目主引擎）

> **5.1 铁律 5·训练驱动**：用真实 CTF 赛题喂 automisc——跑通 → 沉淀工具调用链路到 journal；**跑不通 → 兜底用 AI + ctf-misc / ctf-forensics skill 亲自解题**，不把失败题目当废品扔掉。**每一道失败题必须反哺成 `upgrade/v0.5-train-NNN-{slug}.md`**，记录：失败原因 / AI 兜底思路 / automisc 应该补的能力 / 是否触发架构层迭代。
>
> **5.2 铁律 6·架构优先**（防"单题打补丁"陷阱）：任何针对单题的优化，**必须回答"这能否泛化到同类题目"**。判定标准：
> - ✅ **能泛化**（同模式 ≥ 3 道题命中）→ 走架构层升级（加 router / 加新工具 / 改 toolchain），对应 `upgrade/v0.5-{arch-slug}.md`
> - ❌ **只救这一道**（一次性 trick / 罕见样本）→ 写进训练日志即可，**不动 automisc 代码**，避免工具被特例污染
> - ⚠️ **边界情况**（已知同类但样本少）→ 先写 `upgrade/v0.5-train-NNN-*.md` 观察，**积累 ≥ 3 道同类再升架构**
>
> **5.3 训练会话标准动作**（每跑一道新题按此推进）：
> 1. **跑 automisc**：`python -m automisc run <challenge>` 或 GUI 拖入；记录 journal（工具链 / severity 命中 / 终止点）
> 2. **判定**：
>    - 命中 flag（severity ≥ 5 终止）→ 收 `upgrade/v0.5-train-NNN-{slug}.md` 的"已解"段，标 ✅
>    - 跑完未命中 → 进 step 3
> 3. **AI 兜底**：加载 `ctf-misc` 或 `ctf-forensics` skill，按 skill 指引手动解题（zsteg / binwalk -e / foremost / 十六进制手撕 / strings 启发……）
> 4. **写训练日志**：`upgrade/v0.5-train-NNN-{slug}.md`，含：题目元信息（来源 / 体积 / 类型）/ automisc 失败原因（哪个工具链断在哪）/ AI 兜底步骤 / automisc 应补能力 / 架构判定（5.2 标准的勾选）
> 5. **触发架构迭代**（如 5.2 ✅）：**新建** `upgrade/v0.5-{arch-slug}.md`，**不**直接在训练日志里改 automisc 代码——保持训练日志只描述问题，架构升级走铁律 2 流程
>
> **5.4 失败题归档规范**：
> - 挑战文件放 `tests/fixtures/challenges/{slug}.{ext}`（体积 < 2MB；超 2MB 走仓外）
> - `tests/fixtures/challenges/.gitignore` 排除原文件（`*.png` / `*.zip` / `*.pcap` …），**只 commit 元信息 + 解题描述**
> - journal 关键可疑点（`automisc journal --since` 输出）以代码块贴进训练日志
> - 同模式 ≥ 3 道题 → 在 `STRUCTURE.md §` 加"训练案例索引"段，跨训练日志串起来
>
> **5.5 命名规则**：
> - 训练日志：`upgrade/v0.5-train-NNN-{slug}.md`（NNN 三位序号 001~999，slug 简短描述失败模式）
> - 架构升级：`upgrade/v0.5-{arch-slug}.md`（跟现有命名一致）
> - 训练日志**不**直接实施代码改动；架构升级**不**反向引用单题——单向链路

## 6. AI Agent 特别条款

| ❌ 禁止 | ✅ 允许 |
|---|---|
| 主动修改 `upgrade.md` / `STRUCTURE.md` 之外的文件 | 对未识别需求做"需求澄清"提问（不实施先问）|
| 跳过 `upgrade.md` 直接写代码 | 建议"这看起来是新需求，走铁律 2" |
| commit / PR 描述漏迭代 ID | 引用 `upgrade.md` 迭代行 |
| 推测 / 编造路径 / 函数名 / 任务 ID | 引用 `STRUCTURE.md §2-§5` 速查 |
| 引入 LLM / 云端 / 在线编排（违反完全离线约束）| 治理变更通过后实施 |
| 训练日志直接改 automisc 代码（应走架构迭代）| 写 `upgrade/v0.5-train-NNN-*.md` 沉淀失败案例 |
| 单题补丁绕过铁律 6 架构判定 | ≥ 3 道同类题目再升架构 |
| **`git push` / `gh pr merge` / 删临时分支**（per §2.4）| 打询问卡等 Owner 签字 |

## 7. 文档引用速查

| 想做什么 | 查 |
|---|---|
| 项目结构 + 模块作用 | `STRUCTURE.md` |
| 当前迭代 | `upgrade.md` 索引 + `upgrade/<id>.md` 详细 |
| 修复记录 | `fix.md` 索引 + `upgrade/fix_<bug_name>.md` 详细（per 2026-06-28 治理澄清：`fix_<bug>.md` 在 `upgrade/` 子目录，不在项目根）|
| 历史需求 | `prd.md`（🟡 frozen，仅参考）|
| **训练驱动 / 训练日志 / 架构判定** | `AGENTS.md` §5 |
| 治理 / 铁律 / Git 流程 | `AGENTS.md`（本文件）|

## 8. 治理变更流程

1. Owner 起草变更提案
2. PR 描述写明"**治理变更**" + 原因
3. Owner 自审（**单 Owner 项目** per §2.2 跳过"其他维护者 Review"）
4. 合并后立即通知所有 Owner
5. 变更记录保留在本文档 §9 变更日志

## 9. 变更日志（保留最近 4 条）

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-27 23:25 | **3.3** | **Windows only**（per Owner 2026-06-27 23:25 Y）：v3.2 后 1 小时, Owner Win 端实测 `automisc-gui` 已启动成功 + `extend-tools/` 是 Windows `.exe` → **回退跨平台承诺**，`§2.3 multi-platform` → `Windows only`；**方案 Y · forward commit 收窄**（保留 v3.2 `extend-tools/` 骨架, 删 darwin 代码路径 + 文档改写）；§4 紧急通道 "macOS 紧急修复" → "Windows 紧急修复"；详见 [`upgrade/v0.5-windows-only.md`](upgrade/v0.5-windows-only.md)。7 PR 拆解（PR1 治理+文档 / PR2 平台探测 / PR3 CLI+GUI 元数据 / PR4 extend-tools 平台无关化 / PR5 adapter 描述 / PR6 Core 业务 / PR7 测试）。 |
| 2026-06-27 21:54 | **3.2** | **跨平台 extend-tools/**（per Owner 2026-06-27 Y）— **被 v3.3 收窄为 Windows only**：§2.3 macOS only → multi-platform (macOS + Windows)；新建 `extend-tools/` 目录 (manifest.yaml + install.ps1 + bin/win-x64/) + `src/automisc/tools/paths.py:resolve_tool_binary` (PATH 优先 → extend-tools fallback)；GUI 菜单 `✓/✗` marker 增强（同时检查 binary 可执行）；steghide / zsteg Windows unavailable（zsteg 用 lsb_detect 替代 per v0.5-lsb-detector）；详见 [`upgrade/v0.5-platform-extend-tools.md`](upgrade/v0.5-platform-extend-tools.md)。PR 拆分 4 步（PR1 治理+骨架 / PR2 paths+adapter / PR3 GUI+tests / PR4 验证）。 |
| 2026-06-14 20:37 | **3.1** | **训练驱动 + 架构优先**（per Owner）：§1 加铁律 5 / 6；新增 §5「训练驱动迭代」专章（5.1 铁律定义 / 5.2 架构判定标准 / 5.3 标准动作 / 5.4 归档规范 / 5.5 命名规则）；§5~§8 顺移到 §6~§9。训练日志 `upgrade/v0.5-train-NNN-*.md` 走 gitignore 就地归档（不 commit 原文件）。 |
| 2026-06-13 23:01 | **3.0** | **文档体系 v3.0**：`AGENTS.md` 压到 ≤ 200 行（删 §9 任务快照 / §3-§4 简化 / 变更日志砍到 4 条）；`prd.md` frozen + 跳到 STRUCTURE.md；新增 `STRUCTURE.md` 186 行取代已删 Architecture.md。**净压缩 60% 行数**（1903 → 1160 → ≈ 800）。 |

> 末次归档：2026-06-13（v1.0~v1.19 + v2.0 已归档到 `docs/changelog/AGENTS.md_archived.md`）。
