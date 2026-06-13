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

### 2.5 GitHub 工作流（强制 · 2026-06-13 治理变更）

**远端仓库**：

| 项 | 值 |
|---|---|
| 仓库 URL | <https://github.com/f4cknet/automisc.git> |
| SSH | `git@github.com:f4cknet/automisc.git` |
| HTTPS | `https://github.com/f4cknet/automisc.git` |
| 默认分支 | `main` |
| 默认协议 | HTTPS（CI / AI Agent 默认；用户本地可选 SSH）|

#### 2.5.1 AI Agent Git 操作权限（per Owner 决策，2026-06-13）

> **核心原则**：所有 git 操作（含 3 类高风险远端操作）AI Agent 都有权利执行。每次执行前 AI Agent 必须**打印询问卡**（REMOTE OPERATION REQUEST）→ Owner 在对话中回复 **Y / n / 修改建议** → AI Agent 按回复执行。
>
> **工作模式**：**AI Agent 打申请，Owner 签字，AI Agent 执行**。

**3 类"高风险远端操作"**（每次必须询问 Owner）：

1. **`git push`**（任何远端：push / push --delete / push --force-with-lease 等）
2. **`gh pr merge` / `gh pr create`**（GitHub 平台动作）
3. **删临时分支**（本地 `git branch -D` + 远端 `git push origin --delete`）

**AI Agent 全权操作**（不需询问，但仍记录到 git history）：

- `git add` / `git commit -m` / `git tag`
- `git checkout` / `git switch` / `git branch <new>`
- `git stash` / `git stash pop`
- `git reset --soft`（仅本地撤销，**不**动远端）
- `git merge --no-ff`（本地 merge，**不** push）
- `git rebase`（本地 rebase，**不** push）
- `git cherry-pick`
- `git fetch` / `git log` / `git diff` / `git show`
- 创建/切换本地分支
- 编辑文档文件、写代码、跑测试

**询问模板**（AI Agent 每次高风险操作前必走，Owner 回复 Y 后 AI Agent 立即执行）：

```markdown
===== REMOTE OPERATION REQUEST =====

操作:  gh pr merge 42 --squash --delete-branch
仓库:  https://github.com/f4cknet/automisc.git
PR:    feat/v0.1.0b-PR2-image-stego -> main
理由:  PR2 6 关验收全过；75 unit tests PASS；本地 commit b33de08 已 push 远端
       远端 PR 已开（PR #N）；请求 squash merge + 删除远端 feature 分支

预期结果:
  - main 推进到新 merge commit（包含任务 ID [v0.1.0b-PR2]）
  - 远端 feat/v0.1.0b-PR2-image-stego 分支自动删除（squash merge 默认行为）
  - GitHub 生成 commit SHA 记录到 prd.md §4.1 状态行

不可逆性: 🔴 高（merge 错只能 Revert；删分支只能 reflog / GitHub support 恢复）

请确认: [Y/n/修改后]
==================================
```

**Owner 批量授权机制**（可选加速）：

> 在对话中说一次"批量授权：接下来 PR3-PR9 的所有 push / merge / 删分支都直接执行"，AI Agent **仍打印询问卡**（保留记录），但**不再停下来等回复**——自动按 Y 执行。如有例外，Owner 单次打断。

**事故响应**：

- 错 push：GitHub 网页 Settings → Branches → Delete branch
- 错 merge：GitHub 网页 Revert button（生成 revert commit，不丢历史）
- 错删分支：
  - 本地：`git reflog` 找到 SHA + `git branch <name> <sha>` 恢复
  - 远端：30 天内 GitHub Support 可恢复

#### 2.5.2 每个任务的完整工作流（per 铁律 1 + 2）

```
1. 任务准备（Owner 在本地 main 分支）
   - Owner: git checkout main && git pull
   - 拉任务分支：git checkout -b <type>/<task-id>-<slug>
     （<type> = feat / fix / docs / refactor / test / chore）
     例：git checkout -b feat/v0.1.0b-PR2-image-stego
   - Owner 通知 AI Agent："开干 v0.1.0b-PR2"，并把任务 ID 写到 prompt
   - 在 prd.md §4.x 加任务行 + 状态 🔄（per 铁律 2 步骤 2）
     ⚠️ 这一步 Owner 可让 AI Agent 代写，但提交仍 Owner 来

2. AI Agent 实施 + 文档同步（同一分支内）
   - AI Agent 按 Architecture.md 实施代码 + 测试
   - AI Agent 同分支内更新 prd.md / Architecture.md / tools.md 相关章节
   - **禁止分两个 commit**（per 铁律 3）

3. AI Agent 本地 commit
   - git add -A
   - git commit -m "[v{X}.{Y}.{Z}] {动词} {对象}

     {实施要点}

     6 关验收：
     ② pytest unit 全过（基线 + 新增 N 个）
     ④ 真实样本 smoke：{fixture} → {命中可疑点}
     ⑥ 文档同步（prd.md §4.x + Architecture.md / tools.md）"

4. AI Agent 询问后 push + 开 PR（per §2.5.1）
   - AI Agent 在终端打印"REMOTE OPERATION REQUEST"模板（见 §2.5.1）
   - Owner 回复 Y / n / 修改后
   - Owner 同意后 AI Agent 执行：git push -u origin <branch>
   - AI Agent 在 GitHub 网页开 PR（**Owner 同意**后）
   - 如有 `gh` CLI 可用，AI Agent 也可用 `gh pr create --title ... --body ...`

   PR 标题：[v{X}.{Y}.{Z}] {动词} {对象}（与 commit subject 一致）

   PR 描述模板（AI Agent 提供草稿，Owner 复制粘贴）：
   ```markdown
   ## 任务
   Refs `prd.md §4.x v{X}.{Y}.{Z}` — {任务名}

   ## 实施要点
   - {bullet 1}
   - {bullet 2}

   ## 6 关验收
   - [ ] ① 代码合入 main（PR 合并后由 Owner 打勾）
   - [x] ② pytest unit 全过
   - [ ] ③ {集成 / GUI 测试}（per AGENTS.md §1 铁律 4 关 3）
   - [x] ④ 真实样本 smoke：{描述}
   - [x] ⑤ Owner 自审（per §2.2 单 Owner）
   - [x] ⑥ 文档同步（本 PR 包含 prd.md / Architecture.md / tools.md 更新）

   ## 测试证据
   ```
   $ pytest tests/unit -q
   .......
   73 passed in 1.85s  # 61 baseline + 12 new
   ```

   ```
   $ python -m automisc run --tool {x} --file {fixture}
   exit_code: 0
   suspicious_points (N):
     [5] flag: flag{...}
   ```
   ```

5. AI Agent 询问后 merge（per §2.5.1）
   - AI Agent 在终端打印 merge 询问模板（"REMOTE OPERATION REQUEST"格式，但操作是 `gh pr merge --squash`）
   - Owner 同意后 AI Agent 执行 merge
   - **合并方式**：Squash and merge（保留任务 ID 在 commit message 第一行）
   - 合并后：GitHub 自动删除远端 feature branch

6. AI Agent 任务行状态收尾（在 main 分支，合并完成后）
   - AI Agent 在 main 分支更新 prd.md §4.x 任务行状态 → ✅ + 加实际工时 + commit SHA
   - AI Agent 本地 commit（独立 commit，per §9.4 规则）：
     ```
     [v{X}.{Y}.{Z}-status] mark task complete

     - prd.md §4.x v{X}.{Y}.{Z}: 🔄 → ✅
     - merged commit: <squash merge SHA>
     - actual hours: <h>
     ```
   - **这个 commit 不 push**，等下次任务一起推（避免 1 个 commit / 1 次 push 的浪费）
   - **或者** Owner 单独 push 也可（Owner 决定）

#### 2.5.3 故障排除

| 现象 | 处理 |
|---|---|
| `git push` 报 "Device not configured" | Owner 在本地手动 `git push`（AI Agent 环境无凭据）|
| `git push` 报 "Host key verification failed" | `ssh-keyscan github.com >> ~/.ssh/known_hosts` 后重试，或改 HTTPS |
| 远端 main 比本地新（多人协作场景）| `git pull --rebase` 后再 push feature branch |
| PR 合并后远端分支残留 | GitHub 设置 → "Automatically delete head branches" 开启 |
| AI Agent 误 push | **不可能**（per §2.5.1 硬约束）|

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
| **`git push` / `gh pr merge` / 删临时分支**（AI Agent 全权处理所有 git 操作，但**这 3 类高风险远端操作每次执行前必须先询问 Owner**，per §2.5.1 "AI 打申请 / Owner 签字 / AI 执行" 工作模式）| 帮 Owner 写 commit message / PR 描述草稿 / 终端打印"REMOTE OPERATION REQUEST"等待 Owner 确认 |

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

## 9. Git 仓库 & 工作流速查

> **本节是 §2.5 的速查表 + 状态看板**。详细流程见 §2.5。

### 9.1 远端仓库

| 项 | 值 |
|---|---|
| GitHub URL | <https://github.com/f4cknet/automisc> |
| Clone (HTTPS) | `git clone https://github.com/f4cknet/automisc.git` |
| Clone (SSH) | `git clone git@github.com:f4cknet/automisc.git` |
| 默认分支 | `main` |
| 协议优先级 | HTTPS（CI / AI Agent）> SSH（Owner 本地） |

### 9.2 分支命名约定

| 前缀 | 用途 | 示例 |
|---|---|---|
| `feat/` | 新功能 / 新 adapter | `feat/v0.1.0b-PR2-image-stego` |
| `fix/` | bug 修复 | `fix/v0.1.0b-fix-zsteg-parsing` |
| `docs/` | 纯文档变更 | `docs/v0.1.0b-refine-prd-section-5` |
| `refactor/` | 重构（不改变行为）| `refactor/v0.1.0b-extract-suspicious-module` |
| `test/` | 仅测试补充 | `test/v0.1.0b-PR2-add-zsteg-tests` |
| `chore/` | 杂项（CI / 配置 / 依赖）| `chore/v0.1.0b-update-pyproject-deps` |

### 9.3 commit message 格式

**遵循 Conventional Commits 简化版**（per autopwn 实践经验）：

```
[v{X}.{Y}.{Z}] {动词} {对象}

{1-3 行实施要点}

{可选：6 关验收摘要}
```

**动词词汇**（避免时态混乱）：

- `add` / `implement` / `support`（新功能）
- `fix` / `correct` / `patch`（修复）
- `refactor` / `extract` / `merge`（重构）
- `update` / `clarify` / `sync`（文档）
- `remove` / `drop`（删除）
- `bump` / `upgrade`（依赖升级）

**示例**：

```
[v0.1.0b-PR2] add zsteg + steghide image stego adapters

- tools/steganography/image/{zsteg,steghide_image}.py
- 可疑点：image stego (severity=4) + LSB text (severity=3)
- 12 unit tests / 100% PASS

6 关验收：
② pytest tests/unit: 73 passed (61 baseline + 12 new)
④ 真实样本 smoke：fixture 含 steghide 口令，命中
```

### 9.4 任务状态看板同步规则

| 状态变更 | 时机 | 谁来做 | 远端操作 |
|---|---|---|---|
| `⏳` → `🔄` | PR 创建（AI Agent 推 + 开 PR）| AI Agent 改状态 + commit | 🟡 AI Agent **询问后** push |
| `🔄` → `👀` | PR 开完等自审 | AI Agent 改状态 + commit | 🟡 AI Agent **询问后** push |
| `👀` → `✅` | PR squash merge 进 main + 6 关全过 | AI Agent 改状态 + commit | 🟡 AI Agent **询问后** merge |
| `⏳` / `🔄` → `❌` | 任务不再需要 | AI Agent 改状态 + commit | 🟡 AI Agent **询问后** push |
| 任意 → `⚠️` | 阻塞 | AI Agent 改状态 + commit | 🟡 AI Agent **询问后** push |

> **状态更新与代码 commit 分离**（per §6.1 + `Architecture.md §10`）：状态更新是独立 commit，不进原 PR 的 commit message。这样 git blame 能清楚看到任务看板的演进历史。
>
> **状态更新 commit 可积累**（per §2.5.1）：AI Agent 在 main 分支做状态更新 commit 时，**不立即 push**——等下一次任务一起推（避免 1 commit / 1 push 的浪费）。push 前必须先询问 Owner。

### 9.5 当前任务状态（snapshot · 2026-06-13 14:00 · 重排后）

| 优先级 | 任务 ID | 标题 | 状态 | 备注 |
|---|---|---|---|---|
| **P0** | `v0.1.0b-cleanup` | 文档重整（PR0）| ✅ done | commit `b1643bc`（main 本地，未 push）|
| P1 | `v0.1.0b-PR9` | Python 包基座 | ✅ done | commit `cedea12`（本地，未 push）|
| P2 | `v0.1.0b-PR3` | Forensics/Network（tshark + tcpdump）| ✅ done | commit `da0f5a6`（feat 分支本地，未 push）|
| P3 | `v0.1.0b-PR4` | Stego/Audio+Video（ffmpeg + ffprobe + sox + steghide_audio）| ✅ done | commit `2a3d0fa`（feat 分支本地，未 push）|
| P4 | `v0.1.0b-PR5` | Misc/Archive（sevenz + unzip + john）| ✅ done | commit `813f367`（feat 分支本地，未 push）|
| P5 | `v0.1.0b-PR6` | Forensics/Log（grep + evtx_dump）| ✅ done | commit `待定`（feat 分支本地，未 push）|
| P6 | `v0.1.0b-PR8` | Misc/Brainteaser QR（zbar）| ⏳ | 依赖 PR9 |
| P7 | `v0.1.0b-PR7-envfix` | 前置环境修复（vol.py blocker）| ⏳ | 依赖 PR9 |
| P7 | `v0.1.0b-PR7` | Forensics/Memory（vol.py adapter）| ⚠️ blocker | 依赖 PR7-envfix |
| P8 | `v0.1.0b-encoders` | Encoding 自编写（base/classical/custom）| ✅ done | commit `7eed6c4`（feat 分支本地，未 push）|
| P9 | `v0.1.0b-gui` | GUI 主窗口（PySide6）| ⏳ | 依赖 PR3~PR8 + encoders 全 ✅ |
| — | `v0.1.0b-PR1` | 共享基础工具 6 个 adapter | ✅ done | commit `9401f98` |
| — | `v0.1.0b-PR2` | Stego/Image（zsteg + steghide）| ✅ done | commit `4ca05e5`（PR #2）|
| — | `v0.1.0b-docs` | GitHub workflow 治理 | ✅ done | 含在 PR #2 内 |

> **远端操作状态列说明**（per §2.5.1）：✅ 表示已 push；🟡 表示 AI Agent 已准备好但**未询问 Owner 前不会执行**远端操作。Owner 可在对话中批量授权（如"PR3-PR9 所有 push / merge / 删临时分支都授权你"），AI Agent 收到后仍打印询问卡但不再停下来等回复。

---

---

## 8. 变更日志

> **维护策略**：本表只保留**最近 4 条**（治理/实施重大节点）。超出范围的旧条目按版本号升序归档到 [`docs/changelog/AGENTS.md_archived.md`](./docs/changelog/AGENTS.md_archived.md)。
> **未来规则**：新增条目时追加到表尾；当本表超过 4 条时，最旧的一条移入归档文件并在本表删除。
> 末次归档：2026-06-13（v1.0 / v1.1 / v1.2 / v1.3 已归档）。

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-13 17:15 | **1.13** | **v0.1.0b-PR6 实施完成**：Forensics/Log adapter 落地（grep + evtx_dump）。grep 17 关键字含严重度分级；evtx_dump 集成 python-evtx 0.8.1 + 8 类可疑 EventID + 进程命令行关键字。pyproject.toml 添加 python-evtx 依赖。10 单测 + 1 fixture。144 unit tests PASS。grep 真实样本 smoke 命中 6 个 log_keyword。详见本次 commit。 |
| 2026-06-13 17:05 | **1.12** | **v0.1.0b-PR5 实施完成**：Misc/Archive adapter 落地（sevenz + unzip + john）。sevenz 用 `7z l` + `7z t -p` 探测伪加密。10 单测 + 2 fixture。134 unit tests PASS（PR1 61 + PR2 14 + PR9 22 + PR3 10 + PR4 17 + PR5 10）。真实样本 smoke：伪加密命中 [4]；正常 zip 命中 file count。详见本次 commit。 |
| 2026-06-13 16:55 | **1.11** | **v0.1.0b-PR4 实施完成**：Stego/Audio+Video adapter 落地（5 个新 adapter）。ffmpeg 共享 binary，audio/video 各自独立 name。17 单测 + 2 fixture。124 unit tests PASS（PR1 61 + PR2 14 + PR9 22 + PR3 10 + PR4 17）。真实样本 smoke：ffmpeg_audio/ffprobe/steghide_audio 全命中。详见本次 commit。 |
| 2026-06-13 16:08 | **1.10** | **v0.1.0b-PR3 实施完成**：Forensics/Network adapter 落地（tshark + tcpdump）。tshark 用 `-T fields` CSV 模式 + webshell 关键字白名单。10 单测 + hand-write pcap fixture。107 unit tests PASS（PR1 61 + PR2 14 + PR9 22 + PR3 10）。真实样本 smoke 命中 flag [5] + webshell [4]。详见本次 commit。 |
| 2026-06-13 15:13 | **1.9** | **v0.1.0b-PR9 实施完成**：包基座 smoke（`pip install -e ".[dev]"` + `python -m automisc` + console_script `automisc` 全跑通）。新增 22 单测（包元数据 / 子包 import / CLI main / subprocess），总计 **97 unit tests PASS**（PR1 61 + PR2 14 + PR9 22）。真实样本 smoke 命中 `flag{smoke_test_pr9_xyz}` [5]。详见本次 commit。 |
| 2026-06-13 14:00 | **1.8** | **v0.1.0b-cleanup（PR0）实施完成**：① `prd.md §4.1` 合并两套任务体系为单一 `v0.1.0b-*` 体系；② 按"依赖 + 价值 + 阻塞面"重排 P0~P9 优先级（cleanup → PR9 → PR3~PR8 → PR7-envfix+PR7 → encoders → GUI）；③ `Architecture.md §4.4` 拆"目标布局 + 当前落地"两栏 + `§4.5` PR9 改为包基座；④ 标记 `extend_tools/` 处置。**不引入代码改动**。详见本次 commit。 |
| 2026-06-13 | **1.7** | **§2.5.1 升级 v4**：完全纳入 AI 询问流程（merge 不再 Owner 自助）；批量授权机制启用（per Owner 决策 2026-06-13 12:54）。详见 git history。 |
| 2026-06-13 | **1.6** | **§2.5.1 升级 v3**：细化为"3 类高风险远端操作必询问"，其余全权处理。详见 git history。 |

---

> **最后一条**：
> 文档先行不是繁文缛节，是为了**让团队（包括未来的你和未来的 AI）能在任何时间点快速进入状态**。一次不遵守的代价是后续十次混乱。
>
> **签字栏**：
> - 项目 Owner：@Minzhi_Zhou
> - 首次发布：2026-06-13