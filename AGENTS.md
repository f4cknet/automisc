# AGENTS.md — AutoMisc

> 本文档保留**核心治理规则**（4 条铁律 + AI Agent 条款 + 治理变更流程）
>
> **AI Agent session 启动必读**：
>
> 1. 完整读 `AGENTS.md`（本文件）
> 2. 读 `prd.md`
> 3. 读 `Architecture.md`

---

## 0. 项目一句话

`misc/automisc` 是一个**macOS 平台**、**完全离线**、**PySide6 GUI** 的 CTF Misc 半自动化辅助工具箱。核心交互：拖入题目文件 → 工具菜单触发分析 → 可疑点高亮打印 + journal 自动记录 → 人工决策下一步。架构分层：GUI 层 / Core 调度层 / 工具池层 / 外部工具，**单向依赖**。详细需求见 `prd.md`，架构设计见 `Architecture.md`。

---

## 1. 铁律（不可绕过）

### 铁律 1：实施以 `Architecture.md` 为准

- 任何代码改动必须对应 `prd.md §3` 中的一个任务行（或 Owner 现场新立任务行）
- 在 `prd.md §3` 找不到对应项 ⇒ **该任务不存在**
- 如果你觉得要做的事在 `prd.md` 中没有：先 grep 关键字（确认不是漏看）⇒ 该项是**新需求** ⇒ 立即停手，走铁律 2

### 铁律 2：新需求先更新文档，再实施

**严禁直接实施未经文档记录的新需求**。哪怕需求看起来"显而易见"或"十分钟能搞定"。

新需求包括但不限于：
- 重构过程中冒出的"我顺便改一下这里"
- 同事 / 业务方 / Issue 跟踪中的临时请求
- 看到代码 smell 临时起意的优化
- 工具链调整（CI、依赖、lint 配置、pre-commit、py2app 打包）
- 新增工具适配器 / 新增支持的入口分流类型 / 新增可疑点模式

**强制流程（缺一步都不算完成）**：
1. **架构层**（如需）：加一节或修改既有节（`Architecture.md`），说明为什么 / 影响哪些层 / 哪些模块
2. **执行层**（`prd.md §3`）：加一行任务，含 ID / 状态 / 预估 / Owner
3. **风险层**（如需）：评估风险，写缓解措施
4. **评审**：Owner 自审（单 Owner 项目，per §2.2 简化）
5. **实施**：上述 4 步完成并通过后，才能写代码
6. **追溯**：PR 标题格式 `[v{X}.{Y}.{Z}] {动词} {对象}`，描述必须链接到 `prd.md §3` 章节锚点

### 铁律 3：任务必须有状态

- `prd.md §3` 中**每一行**任务都必须有状态（⏳🔄👀✅⚠️❌ 之一）
- 状态定义：`⏳` 待办 / `🔄` 进行中 / `👀` 待 Review / `✅` 完成 / `⚠️` 阻塞 / `❌` 取消
- 每次代码合并后，必须在**同一 PR** 中更新文档（任务状态 + 实施记录）
- 文档更新与代码改动**禁止分两个 PR**

### 铁律 4：未经验证 = 未完成

"完成"的判定标准（**全部满足**才能把状态改 ✅）：

1. ✅ 代码已合并到 `main` 分支
2. ✅ `pytest -m "not integration"` 全绿（Core 调度层单测，不依赖 GUI）
3. ✅ 若涉及 GUI 行为变更：`pytest -m integration` 跑通对应 GUI 集成测试（拖拽 / 菜单触发 / 输出区渲染）
4. ✅ 若涉及 Core 工具调用行为：在至少 1 个真实 misc 样本上跑一次，对比 journal 关键可疑点命中一致
5. ✅ Owner 自审（单 Owner 项目）
6. ✅ 文档已同步（铁律 3）

**任何一条不满足，状态都不能改 ✅**。

> **关于第 4 条的特殊说明**：automisc 的"完成"判定**不追求 flag 匹配**。automisc 是半自动化辅助工具，最终拿 flag 是用户的事。automisc 的验收是"工具调用成功 + journal 关键可疑点被命中"。

---

## 2. 衍生规则（强化铁律）

### 2.1 任务粒度

- 单个 PR ≤ 400 行 diff（不含 lock 文件）
- 单个 PR 不跨多个任务 ID
- 任务粒度过大 ⇒ 在 `prd.md §3` 中拆分（用 `v{X}.{Y}.{Z}a` / `v{X}.{Y}.{Z}b` 标注）
- GUI 改动和 Core 改动应当分离在不同 PR（GUI 涉及视觉调试，独立 review 周期）

### 2.2 单 Owner 项目简化

- Owner 自审 = Reviewer（不需要第二人签字）
- Owner 转让 = 直接修改 `prd.md §3` 中 Owner 字段并在 PR 描述中说明
- main 是唯一长期分支

### 2.3 Reviewer 责任

Reviewer 验证 PR 是否违反本文档的 4 条铁律 + `prd.md §3` 任务粒度。

### 2.4 macOS only 约束

- 所有 GUI 代码必须在 macOS 上验证（GitHub Actions `macos-latest` runner）
- 不引入跨平台 hack 代码（如 `sys.platform` 分支的特殊处理）
- subprocess 调用外部工具时统一走 macOS 标准 PATH（`/usr/local/bin` / `/opt/homebrew/bin` / 用户 pyenv shims）

---

## 3. 违规与升级

| 等级 | 行为 | 处理 | 恢复 |
|---|---|---|---|
| **L1 轻微** | 文档漏更新但任务已合并 | 补同 PR 文档 | 补完即恢复 |
| **L1 轻微** | PR 标题未引用任务 ID | 改 PR 标题 | 改完即恢复 |
| **L1 轻微** | 任务粒度超 400 行 | 拆完重开 | 拆完即恢复 |
| **L2 中度** | 绕过文档直接实施新需求（铁律 2） | PR 关闭；任务走铁律 2 重新立项 | 走完铁律 2 后恢复 |
| **L2 中度** | 任务标 ✅ 但验收未过 | 状态回退到 👀 或 🔄 | 补完验收恢复 |
| **L3 严重** | 伪造验收 | 撤销 PR；Owner 暂停认领新任务一周 | 一周冷却期后恢复 |
| **L3 严重** | 反复违反铁律 2 / 4 | 撤销该 Owner 资格 | 需 Owner 重新授权 |

---

## 4. 紧急通道

以下三种情况可临时跳过铁律 2（**仅铁律 2**，铁律 1/3/4 永远不能跳过）：

1. **macOS 系统类紧急修复**（如 PySide6 版本兼容问题导致 GUI 无法启动）：必须 24h 内补走铁律 2
2. **CI 全红且阻塞合入**（hotfix 模式）：文档更新必须同 PR 跟上
3. **Owner 明确授权的临时特批**：必须在 PR 描述中写明原因 + 授权人

**其他一切情况，铁律不可绕过。**

---

## 5. AI Agent 特别条款

任何参与本项目的 AI Agent **在每个 session 启动时必须按序执行**：

1. 读取本文件（`AGENTS.md`）——完整
2. 读取 `prd.md` 整个 §0-§9 —— 完整
3. 读取 `Architecture.md §1 分层模型` + `§3 Core 调度层` —— 完整
4. 读取 `prd.md §3` 中**当前任务**相关行

**硬性约束**：

| ❌ 禁止 | ✅ 允许 |
|---|---|
| 主动修改 `prd.md` / `Architecture.md` 之外的文件 | 对未识别的需求做"需求澄清"提问（不实施，先问） |
| 跳过 `prd.md §3` 直接生成代码 | 建议"这看起来是新需求，建议走铁律 2" |
| 在 PR 描述 / commit message 中遗漏任务 ID | 引用 `prd.md §3` 任务行 |
| 推测 / 编造文件路径、函数名、任务 ID | 引用 `Architecture.md §3 Core 调度层` + `§6 plug-in 机制` 文件路径速查 |
| 跨多个任务 ID 同时改代码 | 一次只动一个任务 ID |
| 把现有代码逻辑"复述"而不抽到新层 | 严格遵守 `Architecture.md §1` 的分层依赖方向 |
| **引入 LLM / 云端服务 / 在线编排决策**（违反 `prd.md §2` 非范围约束） | 仅在 `prd.md §10` 治理变更流程通过后实施 |

> **关键自检**：每次输出代码前，AI Agent 必须在内部回答"这个改动对应 `prd.md §3` 哪一行？对应 `Architecture.md` 哪一节？"，回答不出就停手。

---

## 6. 文档引用速查

| 你想做什么 | 查 |
|---|---|
| 怎么开发 automisc | `prd.md` §0-§9 |
| 找当前任务 | `prd.md §3` 任务看板 |
| 理解 4 层架构 | `Architecture.md §1 分层模型` |
| 工具池清单 + 适配器说明 | `tools.md`（待 Owner 整理外部工具清单后建立）+ `Architecture.md §6 plug-in` |
| 入口分流规则（文件类型 → subflow） | `prd.md §5` |
| 可疑点统一 schema | `prd.md §6` |
| 演进路线图 | `prd.md §9` |
| GUI 设计要点 | `Architecture.md §2` |
| Core 调度层 API | `Architecture.md §3` |
| 与 skill 体系的关系 | `Architecture.md §5`（明确**不桥接**） |
| **修复记录索引** | `fix.md`（v0.1+ 治理，**只**列已 merge fix） |
| **单 fix 详细记录** | `fix_<bug_name>.md`（per §6.1） |

---

### 6.1 修复记录文件结构（v0.1+ 治理 · 2026-06-13）

**目的**：避免 `fix.md` 在迭代中累积成超大文件。

- **`fix.md` = 索引**（~50 行）—— 只列已 merge 的 fix（含 fix ID / 关联任务行 / 文件链接 / 一句话描述 / 状态）
- **`fix_<bug_name>.md` = 单 fix 完整记录**（~80-200 行）—— 类比 git feature branch 命名
- **未做 / TODO** → 走 `prd.md §3` 任务看板，**不进** `fix.md`

**命名约定**：
- `bug_name` 用 snake_case（如 `pyside6_drag_drop` / `binwalk_adapter_parse`）
- 必须能描述 root cause 或 fix 策略

**新增流程**（per 铁律 2）：

1. fix 立项：在 `prd.md §3` 加任务行（状态 `⏳`），同时在 `fix.md` 索引加占位行（status=`⏳ TODO`，文件可暂不创建）
2. fix 实施：完成代码 + 6 关验收后，在 squash merge 提交里**同时**写 `fix_<bug_name>.md` + 更新 `fix.md` 索引（status=`✅`）
3. 任务行状态同步：fix merge 后，`prd.md §3` 任务行状态改 `✅`

**删除规则**：
- `fix_<bug_name>.md` 不删除（永久保留 — fix 是事实记录，git blame / 未来 audit 追溯用）
- 改名 / 拆分 / 合并 走治理变更

**例外**（不新建 `fix_<bug_name>.md` 的 fix）：
- 单行 typo / 注释错别字
- 测试 fixture 调整
- 文档勘误（`AGENTS.md` / `prd.md` / `Architecture.md` 自身）
- 治理变更本身（per §7）
- GUI 视觉细节微调（颜色 / 间距）
—— 这些直接 squash merge 进 main，不进 `fix.md` 索引

---

## 7. 治理变更

本文件的修改需要：

1. **Owner 起草**变更提案
2. 在 PR 描述中写明 **"治理变更"** + 原因
3. Owner 自审（**单 Owner 项目** per §2.2 — 跳过"其他维护者 Review"）
4. 合并后**立即通知**所有 Owner（issue / 群通知；单 Owner 项目 no-op）
5. 重要变更应回填到 `prd.md` / `Architecture.md`

> 治理变更记录保留在本文件 §8"变更日志"，不允许只写在 PR 描述里。
> 治理变更在**主干开发**模式下合并即可（PR target=`main`）——不需要"dev 集成分支"中间层。

---

## 8. 变更日志

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-13 | 1.0 | 初版：4 条铁律 + L1/L2/L3 违规分级 + 紧急通道 + AI Agent 精简条款（3 条核心）+ macOS only 约束（§2.4）+ 治理变更流程。骨架参考 `pwn/autopwn/AGENTS.md v1.7`，按 automisc 特性调整：铁律 4 完成判定改写（不追求 flag 匹配）；文档契约改为 `AGENTS.md` + `prd.md` + `Architecture.md` 三件套（无独立 `upgraded.md`，任务看板合并入 `prd.md §3`）；明确不引入 LLM / 不桥接 skill 体系 |
| 2026-06-13 | 1.1 | **v0.1.0b-PR1 实施完成**（per `prd.md §4.1 v0.1.0b-PR1`）：实现 core/ + tools/shared/ 6 个 adapter + 61 unit tests 100% PASS + 真实样本 smoke 通过 6 关验收。**文档契约首次实战**：任务状态 🔄 → ✅ + `Architecture.md §10` + `tools.md §8` + 本表同步更新；代码与文档严格同 PR 落地 |

---

> **最后一条**：
> 文档先行不是繁文缛节，是为了**让团队（包括未来的你和未来的 AI）能在任何时间点快速进入状态**。一次不遵守的代价是后续十次混乱。
>
> **签字栏**：
> - 项目 Owner：@Minzhi_Zhou
> - 首次发布：2026-06-13