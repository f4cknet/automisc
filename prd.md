# prd.md — AutoMisc 产品需求文档

> **角色**：automisc 的**需求 + 任务看板 + 工具池 + 演进路线**单一事实来源
> **状态**：v0.1 启动（2026-06-13）
> **配套文档**：
> - [`AGENTS.md`](./AGENTS.md) — 项目治理（4 条铁律 + 违规分级 + 紧急通道 + AI Agent 条款）
> - [`Architecture.md`](./Architecture.md) — 系统架构设计（4 层分层 + 模块依赖 + plug-in 机制 + 验证方法）
> - [`tools.md`](./tools.md) — 外部 misc 工具清单（待 Owner 整理后建立） + adapter 适配说明
>
> **本文档章节**：
> - §0 产品定位
> - §1 用户故事
> - §2 范围 & 非范围（含硬约束）
> - §3 任务看板（v0.1 / v0.5 / v1.0）
> - §4 工具池初版（占位）
> - §5 入口分流表（文件类型 → subflow）
> - §6 可疑点格式（统一 schema）
> - §7 完成判定
> - §8 GUI 形态
> - §9 演进路线图
> - §10 治理变更流程

---

## 0. 阅读指引

| 你是谁 | 先看哪一节 |
|---|---|
| **第一次接触本项目** | **必读 [`AGENTS.md`](./AGENTS.md) §1 铁律** → 本文件 §0 → §2 → §3 → §9 → [`Architecture.md §1`](./Architecture.md) |
| **想认领任务** | §3 任务看板 → §9 演进路线 |
| **正在做某个任务** | §3 当前任务 → [`Architecture.md §7 验证方法`](./Architecture.md) |
| **理解 4 层架构** | [`Architecture.md §1`](./Architecture.md) + §3 Core 调度层 |
| **AI Agent session 启动** | [`AGENTS.md §5`](./AGENTS.md) 4 步启动 → 本文件 §0-§9 |
| **理解为什么 automisc 不桥接 skill** | [`Architecture.md §5`](./Architecture.md) |

---

## 1. 产品定位

`misc/automisc` 是一个**macOS 平台**、**完全离线**、**PySide6 GUI** 的 CTF Misc 半自动化辅助工具箱。

### 1.1 一句话定位

> **拖入题目文件 → 工具菜单触发分析 → 可疑点高亮打印 + journal 自动记录 → 人工决策下一步。**

### 1.2 与"随波逐流"等传统 misc 工具的关系

| 维度 | 随波逐流 | automisc（本项目）|
|---|---|---|
| 形态 | Windows GUI | macOS GUI（PySide6）|
| 工具池 | 50+ 编码/隐写/取证工具 | 同等规模 + 可扩展 |
| 入口分流 | 用户手动选工具 | **自动路由**（文件类型 → subflow）|
| 可疑点提示 | 文本展示 | **高亮 + 结构化**（统一 schema）|
| 多步编排 | 无（纯手动）| **预留路线**：v0.5 模板 → v1.0 DAG |
| journal 记录 | 无 | **自动积累**（每次工具调用 = 一段）|

### 1.3 与 autopwn 的根本差异

| 维度 | autopwn | automisc |
|---|---|---|
| 目标 | 全自动拿 root shell | 半自动化找 flag 线索 |
| 完成判定 | `verify_shell` 真拿到 `uid=0` | 可疑点列表 + journal（**不**追求 flag 匹配）|
| 决策路径 | 优先级排序的策略链 | 人工决策（GUI 触发 → 可疑点 → 用户决定下一步）|
| 工具调用深度 | 链式（strategy 内部多次调用）| 单次（一次工具 = 一次可疑点扫描）|
| 报告产物 | docx 报告（CTF 提交用）| solve_journal.md（per misc-skill 约定）|

---

## 2. 用户故事

### US-1：比赛场景（核心场景）

> **作为 CTF 参赛选手，我在比赛现场拿到一个 misc 题目附件，希望：**
> 1. 把附件拖入 automisc 主窗口
> 2. 看到 automisc 自动识别文件类型 + 推荐初始 subflow（如"PNG 文件，建议尝试图片隐写"）
> 3. 在工具菜单里点击 `foremost`（图片隐写分类下），看到输出区实时滚动 foremost 进度
> 4. foremost 完成，看到输出区高亮显示"分离出 3 个文件：1.zip / 2.png / 3.bin"
> 5. 把 `1.zip` 拖入新菜单继续（重复 1-4 步）
> 6. 比赛结束后，从 journal 面板导出完整解题路径

### US-2：练习场景（流量分析）

> **作为 CTF 选手，我在练习 webshell 流量分析题，希望：**
> 1. 拖入 `attack.pcap`
> 2. automisc 自动识别"pcap 文件"，引导我到流量分析 subflow
> 3. 点击工具 `tshark 提取 HTTP`，输出区显示"提取出 47 个 HTTP 请求"
> 4. 点击工具 `webshell 家族识别`，输出区高亮"识别到 3 个冰蝎 v3.0 payload + 1 个菜刀 payload"
> 5. 点击 `base64 解码`，选中第 2 个 payload 解码，看到解码后的 webshell 代码
> 6. journal 自动记录每一步（工具 + 参数 + 结果摘要 + 关联可疑点 ID）

### US-3：赛后复盘

> **作为参赛选手，比赛结束想整理 writeup，希望：**
> 1. 打开 automisc journal 面板
> 2. 看到本次比赛所有题目按时间排序的工具调用记录
> 3. 点击"导出 journal"，生成 `solve_journal.md`
> 4. 复制 markdown 内容到 writeup

---

## 3. 范围 & 非范围（含硬约束）

### 3.1 范围（v0.1 必须做）

- ✅ PySide6 GUI 主窗口（macOS 单窗口布局）
- ✅ 文件拖拽接收（单文件 + 多文件）
- ✅ 工具菜单分类（隐写 / 流量 / 压缩 / 内存 / 编码 / 取证 六大类）
- ✅ 入口分流（文件类型 → subflow 推荐）
- ✅ 工具池：至少 5 个 adapter 跑通（binwalk / strings / foremost / tshark / vol.py 之一）
- ✅ 输出区（实时滚动 + ANSI 高亮）
- ✅ 可疑点扫描器（统一 schema）
- ✅ journal 自动记录
- ✅ 6 关验收（per `AGENTS.md §1` 铁律 4）

### 3.2 非范围（硬约束）

| ❌ 不做 | 原因 |
|---|---|
| **不引入 LLM 编排决策** | 完全离线产品，不依赖任何 AI 服务 / 在线 API |
| **不桥接 `misc/skills/*SKILL.md`** | 那些 skill 是给 AI Agent 用的，automisc 是独立离线工具（per `Architecture.md §5`）|
| **不做跨平台（仅 macOS）** | macOS only（per `AGENTS.md §2.4`）|
| **不做全自动拿 flag** | 半自动化辅助，最终决策权在人 |
| **不追求 flag 匹配作为完成判定** | automisc 验收是"工具调用成功 + 可疑点命中"，不是 flag 正则 |
| **不做云端同步 / 远程服务 / Web UI** | 完全离线桌面工具 |
| **v0.1 不打包成 `.app`**（占位章节）| 开发期 `python -m automisc` 启动；v0.3 再评估 py2app（per `AGENTS.md §2.4` 占位）|
| **v0.1 不做编排模板**（占位章节）| 仅手动菜单触发；v0.5 起引入模板（per §9）|

### 3.3 占位章节（TBD · 待 Owner 决策）

- ⏳ **Q2 打包策略**：v0.1 是否接 py2app 打成 `.app`？（建议先不打包）
- ⏳ **Q3 GUI 布局**：单窗口 / 多窗口 / MDI？（建议单窗口）

---

## 4. 任务看板

> **任务 ID 格式**：`v{X}.{Y}.{Z}` — 例如 `v0.1.0` / `v0.5.0` / `v1.0.0`
> - `X` 主版本（架构重大变更）
> - `Y` 次版本（功能演进，如编排档位升级）
> - `Z` 修订版本（bug 修复 / 工具池新增）

### 4.1 v0.1 启动（最小可用 GUI · 当前 sprint）

> **2026-06-13 14:00 重整说明**：本节原列两套并行任务体系（`v0.1.0~v0.1.10` 旧编号 + `v0.1.0b~PR9` 新编号），互相重叠矛盾。
> **重整结果**：以 `v0.1.0b-*` 体系为**唯一事实来源**（对应代码实际状态 + AGENTS.md §9.5 状态看板）。
> 旧编号已废止，PR3~PR9 + cleanup + GUI + encoders 10 项任务已按依赖重排。

| 优先级 | ID | 任务 | 状态 | 预估 | 备注 |
|---|---|---|---|---|---|
| **P0** | `v0.1.0b-cleanup` | **文档重整（PR0 · 阻塞后续）**：合并 prd.md §4.1 两套体系为单一一套；清理 `Architecture.md §4.4 / §4.5` 中尚未落地的"假目录"（forensics/ misc/ encoders/ gui/）；标记 `extend_tools/` 处置（png_crc_check / F5 / volatility2 是历史遗留杂物，按铁律 2 列入后续清理 PR，不在本 PR 删代码）；新增 §4.5 重排优先级表说明本次决策 | ✅ | 1h | **已完成**（commit `b1643bc`，2026-06-13 14:07）；**不引入代码改动**；**6 关验收**：② N/A（无单测）；③ N/A（无 GUI）；④ N/A（无 Core 工具行为）；⑥ ✅ 文档同步（本 PR 即文档）；①/⑤ 本地 commit + 单 Owner 自审 = 等 Owner push 后再勾 |
| P1 | `v0.1.0b-PR9` | **Python 包基座补完**：pyproject.toml 已写但 `python -m automisc` 未验证；补 `src/automisc/__main__.py` 入口 + dev install smoke + console_script 跑通 | ✅ | 1.5h | **已完成**（commit `cedea12`，2026-06-13 15:13）；**依赖**：cleanup；**6 关验收**：② ✅ `pytest tests/unit` 全过（**97 passed** = PR1 61 + PR2 14 + PR9 22）；③ N/A（无 GUI）；④ ✅ 真实样本 smoke：`automisc run --tool strings --file tests/fixtures/sample_text.txt` 命中 `flag{smoke_test_pr9_xyz}` [5]；⑥ ✅ 文档同步；①/⑤ 待 Owner push + merge 后勾 |
| P2 | `v0.1.0b-PR3` | Forensics/Network（tshark + tcpdump adapter）| ✅ | 3h | **已完成**（commit `da0f5a6`，2026-06-13 16:08）；**依赖**：PR9；按 PR1 模板复制；**6 关验收**：② ✅ `pytest tests/unit` 全过（**107 passed** = PR1 61 + PR2 14 + PR9 22 + PR3 10）；③ N/A（无 GUI）；④ ✅ 真实样本 smoke：`automisc run --tool tshark --file tests/fixtures/sample_http_flag.pcap` 命中 flag [5] + webshell [4]（hand-write 经典 pcap，含 2 HTTP packet：GET /flag{pr3_smoke_tshark_xyz} + POST /shell.php 含 eval/base64_decode）；tcpdump 同样命中；⑥ ✅ 文档同步；①/⑤ 待 Owner push + PR 后勾 |
| P3 | `v0.1.0b-PR4` | Stego/Audio + Video（ffmpeg_audio + ffprobe + ffmpeg_video + sox + steghide_audio）| ✅ | 4h | **已完成**（commit `2a3d0fa`，2026-06-13 16:55）；**依赖**：PR9；**6 关验收**：② ✅ `pytest tests/unit` 全过（**124 passed** = PR1 61 + PR2 14 + PR9 22 + PR3 10 + PR4 17）；③ N/A（无 GUI）；④ ✅ 真实样本 smoke：`automisc run --tool ffmpeg_audio --file tests/fixtures/sample_audio_flag.wav` 命中 flag [5] + duration=1.00s + audio_stream（pcm_s16le 44100Hz mono）；`ffprobe --file sample_video_flag.mp4` 命中 flag [5] + 2 streams + duration=1.00s；`sox --file` sample_rate=44100；`steghide_audio` 命中 capacity 2.7KB + unavailable tty 信号；⑥ ✅ 文档同步；①/⑤ 待 Owner push + PR 后勾 |
| P4 | `v0.1.0b-PR5` | Misc/Archive（sevenz + unzip + john）| ⏳ | 4h | **依赖**：PR9；⚠️ john-jumbo 需 `brew install john-jumbo`（v0.1 必装）|
| P5 | `v0.1.0b-PR6` | Forensics/Log（grep + evtx_dump）| ⏳ | 2.5h | **依赖**：PR9；⚠️ evtx_dump 需 `pip install python-evtx` |
| P6 | `v0.1.0b-PR8` | Misc/Brainteaser QR（zbar）| ⏳ | 2h | **依赖**：PR9；⚠️ zbar 需 `brew install zbar`（v0.1 必装）|
| P7 | `v0.1.0b-PR7-envfix` | **前置环境修复（解决 vol.py blocker）**：在 Apple Silicon 上 brew 装 volatility2 / 或 python 装 `pip install volatility3` 二选一；选好方案后 ADR 写进 `tools.md §3.1` | ⏳ | 1h | **依赖**：PR9；**不写 adapter**，只解决"装得上" |
| P7 | `v0.1.0b-PR7` | Forensics/Memory（vol.py adapter）| ⚠️ | 3h | **依赖**：PR7-envfix；⚠️ blocker 在 PR7-envfix |
| P8 | `v0.1.0b-encoders` | **Encoding 自编写（9h Python 模块）**：`core/encoders/base.py`（base16/32/58/62/64/85/91/2048/32768/65536）+ `core/encoders/classical.py`（ROT13/47/18 + Caesar + Vigenère + Atbash + Pigpen + Keyboard Shift + Affine + Rail Fence）+ `core/encoders/custom.py`（BCD + IEEE 754 + UTF-16 endianness + Unicode Tags/Variation Selector + Multi-layer auto-decoder）+ 单元测试 | ⏳ | 9h | **依赖**：PR9；可与 PR3~PR8 并行；非工具池层（per Architecture.md §4.4）|
| P9 | `v0.1.0b-gui` | GUI 主窗口（PySide6 QMainWindow + 文件拖拽 + 菜单树 + 输出区 + journal 面板）| ⏳ | 8h | **依赖**：PR3~PR8 + encoders 全 ✅；**放最后**——所有 adapter 跑通再做 GUI 集成，避免改 22 个 adapter 时 GUI 测试跟着改 |
| — | `v0.1.0b-PR1` | **共享基础工具 6 个 adapter**（file / strings / binwalk / foremost / exiftool / xxd）+ tools/base.py + core/suspicious.py + core/registry.py + core/orchestrator.py + core/result.py + 单元测试 | ✅ | 4h | **已完成**（per AGENTS.md §9.5）；**6 关验收**：① ✅ commit `4ca05e5`；② ✅ 61 tests PASS；③ N/A；④ ✅ fixture smoke 命中 flag/file_header/base64；⑤ ✅ Owner 自审；⑥ ✅ 文档同步 |
| — | `v0.1.0b-PR2` | **Stego/Image 主工具**（zsteg + steghide adapter）+ 单元测试 | ✅ | 4h | **已完成**（per AGENTS.md §9.5）；**6 关验收**：① ✅ commit `4ca05e5`；② ✅ 75 passed（PR1 61 + PR2 14）；③ N/A；④ ✅ zsteg LSB PNG 命中 `flag{pr2_smoke_lsb_xyz}` [4]；⑤ ✅ Owner 自审；⑥ ✅ 文档同步 |
| — | `v0.1.0b-docs` | GitHub workflow 治理（AGENTS.md §2.5 + §8 变更日志）| ✅ | 1h | **已完成**（per AGENTS.md §9.5）；非代码 PR，纯治理 |

**v0.1 总预估**：~39h（按 6h/人/天 ≈ 6.5 天）+ 清理 + 环境修复 = ~41h
- 已完成：9h（PR1 4h + PR2 4h + docs 1h）
- 待实施：32h（cleanup 1h + PR9 1.5h + PR3~PR8 18.5h + encoders 9h + GUI 8h - 部分依赖重叠）

**实施顺序**（per `AGENTS.md §2.1` 任务粒度约束 ≤400 行 / PR）：
1. 🔄 **cleanup**（P0，当前）→ 1h
2. ⏳ **PR9**（包基座）→ 1.5h
3. ⏳ **PR3** → 3h ｜ ⏳ **PR4** → 4h ｜ ⏳ **PR5** → 4h ｜ ⏳ **PR6** → 2.5h ｜ ⏳ **PR8** → 2h ｜ ⏳ **PR7-envfix** → 1h + **PR7** → 3h ｜ ⏳ **encoders** → 9h
   - PR3~PR8 + encoders 互相无依赖，可并行（人不够时分批）
4. ⏳ **GUI** → 8h（最后做）

**决策记录**（2026-06-13 14:00）：
- **为什么 cleanup 第一**：铁律 1 要求"代码改动必须有 prd.md 对应行"；现在 prd 自己矛盾，再不重整后续 PR 的文档同步无法可依
- **为什么 PR9 第二**：pyproject.toml 写了但没 smoke 验证；PR3 跑 smoke 需要 `python -m automisc` 真能起来
- **为什么 PR7（Memory）放后面**：vol.py 安装是 blocker；拆出 PR7-envfix 单独解决"装得上"，避免污染 PR7 的代码 PR
- **为什么 GUI 最后**：避免改 22 个 adapter 时 GUI 集成测试跟着改 22 次；adapter 全跑通再做 GUI 集成测试效率最高
- **为什么 encoders 与 PR3~PR8 并行**：非工具池层（per `Architecture.md §4.4`），与 adapter 无耦合

### 4.2 v0.5 候选（工具链模板编排）

> **本阶段在 v0.1 完成后 Owner 启动新 sprint 拍板，本表占位**。

| ID | 任务 | 状态 | 预估 | 备注 |
|---|---|---|---|---|
| `v0.5.0` | **编排模板引擎**：`core/orchestrator/template.py` 定义 `Template` 抽象类 + 顺序执行工具 | ⏳ | 4h | 见 `Architecture.md §8` 演进路径 |
| `v0.5.1` | **3 个预设模板**：pcap_webshell_check / image_stego_check / archive_crack | ⏳ | 6h | 每个模板 ≈ 2h |
| `v0.5.2` | **GUI "自动分析"按钮**：菜单点击 → 选模板 → 自动执行 | ⏳ | 3h | |
| `v0.5.3` | **macOS 打包评估**：py2app / PyInstaller 二选一实测 | ⏳ | 4h | 视 v0.1-Q2 决策 |

### 4.3 v1.0 候选（DAG 编排）

> **本阶段在 v0.5 完成后 Owner 启动新 sprint 拍板，本表占位**。

| ID | 任务 | 状态 | 预估 | 备注 |
|---|---|---|---|---|
| `v1.0.0` | **工具输出 type system**：每个 adapter 声明产出数据类型（`extracted_files` / `text_strings` / `decoded_text` 等）| ⏳ | 6h | DAG 编排的前置 |
| `v1.0.1` | **DAG 引擎**：`core/orchestrator/dag.py` 根据数据依赖自动触发下一节点 | ⏳ | 8h | |
| `v1.0.2` | **GUI 编排视图**：可视化当前 DAG 节点状态（pending / running / done / failed）| ⏳ | 4h | |
| `v1.0.3` | **手动干预**：右键节点跳过 / 重跑 / 标记关键 | ⏳ | 3h | |

### 4.4 open 阻塞（当前 = 0）

_（无 — 2026-06-13 v0.1 启动时无新阻塞）_

---

## 5. 工具池

> **工具池完整清单见 [`tools.md`](./tools.md)**。本节仅说明工具池与 automisc 的整体关系 + adapter 模式约定。

### 5.1 工具池分类（按分支 · per §4.1 v0.1.0b 2026-06-13 重大重整）

> **从"按工具能力分类"改为"按用户面对的题目类型分支"**，详细架构决策见 [`tools.md §2`](./tools.md)。

| 一级分支 | 子分支数 | 工具数（✅/⚠️/❌）| v0.1 P0 | 详情 |
|---|---|---|---|---|
| **Forensics（取证）** | 4 | 14（6✅ / 1⚠️ / 7❌）| 6 | [`tools.md §3.1-3.4`](./tools.md) |
| **Steganography（隐写术）** | 3 | 22（9✅ / 1⚠️ / 12❌）| 8 | [`tools.md §3.5-3.7`](./tools.md) |
| **Encoding（编码分析）** | 3 | **0**（内置实现）| 9h Python 模块 | [`tools.md §3.8`](./tools.md) |
| **Misc Others（其他）** | 3 | 10（5✅ / 0⚠️ / 5❌）| 3 | [`tools.md §3.9-3.11`](./tools.md) |
| **共享基础工具** | — | 8（8✅ / 0⚠️ / 0❌）| 5 | [`tools.md §3.12`](./tools.md) |
| **合计** | **14** | **54**（28✅ / 2⚠️ / 24❌）| **22** | — |

**11 个 subflow 全清单**（含 Encoding 子分支）：
- **Forensics** 4：Memory Forensics / Disk Forensics / Network Forensics / Log Forensics
- **Steganography** 3：Image Stego / Audio Stego / Video Stego
- **Encoding** 3（**自编写**）：Base 系列 / 古典密码 / 自定义编码
- **Misc Others** 3：Archive / Office / Brainteaser

**删去的旧 subflow**（per `§2.2` 非范围约束 + 2026-06-13 Owner 决策）：
- ❌ OSINT（开源情报）—— 与 automisc "完全离线" 产品定位冲突
- ❌ Blockchain（区块链）—— automisc 不做
- ❌ Games & VMs（游戏题 / VM 题）—— automisc 不做
- ❌ 二进制分析（独立 subflow）—— strings / file / binwalk / xxd 等基础工具下沉到各分支共享
- ❌ 文档分析（独立 subflow）—— 归入 Misc Others / Office

> **P0 = v0.1 必须包含的 adapter**（per §4.1 v0.1.6，要求 ≥5 个）；当前 **22 个 P0 adapter**，分 9 个 PR 实施（per [`tools.md §6.2`](./tools.md)）。
> 完整 P0 工具列表见 [`tools.md §6`](./tools.md)。

### 5.2 adapter 模式

每个工具 = 一个 Python adapter，结构：

```python
from automisc.tools.base import ToolAdapter, ToolResult

class BinwalkAdapter(ToolAdapter):
    name = "binwalk"
    category = "binary_analysis"
    description = "扫描并提取文件中的嵌入文件"

    def run(self, file_path: str) -> ToolResult:
        # subprocess 调 binwalk
        # 解析输出
        # 提取可疑点（PK / jpg / rar 等文件头）
        return ToolResult(
            tool_name=self.name,
            exit_code=0,
            stdout=...,
            suspicious_points=[...]
        )
```

详细 adapter 规范见 [`Architecture.md §6 plug-in 机制`](./Architecture.md)。

### 5.3 工具池治理流程

新增工具 / 修改工具状态 / 调整 P0 优先级，都需要：

1. **更新 [`tools.md`](./tools.md)**：增删改对应工具行（状态 / 路径 / 安装指引）
2. **更新本文件 §5.1 总表**：分类汇总数同步
3. **若新增 P0 工具**：在 [`prd.md §4`](./prd.md) 任务看板加对应 adapter 任务行（per `AGENTS.md §1` 铁律 2）

---

## 6. 入口分流表

> **文件类型 → subflow 推荐**。GUI 拖拽文件时，automisc 自动给出推荐。
> **2026-06-13 重整**（per §4.1 v0.1.0b）：从 9 个旧 subflow 重排为 **11 个新 subflow**（4 Forensics + 3 Stego + 3 Encoding + 3 Misc Others，编码子分支无外部工具依赖）。

### 6.1 主分流表（按分支）

| 文件类型（识别依据）| 一级分支 | subflow | 推荐初始工具 |
|---|---|---|---|
| `.vmem / .raw / .dmp / .core` | **Forensics** | Memory Forensics | vol.py imageinfo + strings |
| `.dd / .img / .E01 / .vmdk / .ova / .vhd` | **Forensics** | Disk Forensics | 7z 解压 / photorec / testdisk |
| `.pcap / .pcapng / .cap` | **Forensics** | Network Forensics | tshark 提取 HTTP + webshell 家族识别 |
| `.log / .evtx / .evtx.bz2 / auth.log` | **Forensics** | Log Forensics | grep + awk + sed / evtx_dump |
| `.png / .jpg / .bmp / .gif / .webp` | **Steganography** | Image Stego | exiftool + zsteg + foremost + binwalk |
| `.wav / .mp3 / .flac / .ogg / .aac` | **Steganography** | Audio Stego | ffmpeg 频谱 + sox + steghide |
| `.mp4 / .mkv / .avi / .mov / .flv` | **Steganography** | Video Stego | ffprobe 多 stream 提取 + ffmpeg 帧 |
| **任何编码可疑文本**（base64/32/58/62/64/85/hex/古典密码）| **Encoding** | Base / 古典 / 自定义 | （**内置实现**）`core/encoders/base.py` + `classical.py` + `custom.py` |
| `.zip / .rar / .7z / .tar.gz / .tar.bz2 / .tar.xz` | **Misc Others** | Archive | 7z / unzip + 伪加密检查 + john 4-6 位爆破 |
| `.docx / .pdf / .xlsx / .pptx` | **Misc Others** | Office | exiftool + binwalk + python-docx |
| **二维码 / 条码**（图片含 QR/Barcode 特征）| **Misc Others** | Brainteaser | zbarimg（缺失）/ pyzbar（fallback）|
| `.sql / .db / .sqlite` | **Misc Others** | Brainteaser | sqlite3 + strings |
| **未知 / 无后缀 / magic bytes 异常** | **共享基础** | 通用入口 | file + strings + binwalk + foremost + xxd |

### 6.2 文件 → 一级分支决策树

```
任意文件
    │
    ├── 文件 magic 是 vmem/raw/dmp?  ──→ Forensics / Memory
    ├── 文件 magic 是 dd/img/E01/vmdk? ──→ Forensics / Disk
    ├── 文件 magic 是 pcap?       ──→ Forensics / Network
    ├── 文件 magic 是 log/evtx?   ──→ Forensics / Log
    │
    ├── 文件 magic 是 png/jpg/bmp/gif/webp?  ──→ Stego / Image
    ├── 文件 magic 是 wav/mp3/flac/ogg?      ──→ Stego / Audio
    ├── 文件 magic 是 mp4/mkv/avi/mov/flv?   ──→ Stego / Video
    │
    ├── 文件 magic 是 zip/rar/7z/tar?  ──→ Misc Others / Archive
    ├── 文件 magic 是 OLE/zip+xml?     ──→ Misc Others / Office (docx/xlsx/pptx)
    ├── 文件 magic 是 %PDF?           ──→ Misc Others / Office
    │
    ├── 文件内容是 base64/32/58/62/64/85/hex 字符串? ──→ Encoding / Base 系列
    ├── 文件内容是 ROT13/Caesar 等字符替换?    ──→ Encoding / 古典密码
    ├── 文件内容是 BCD/IEEE754/Unicode Tags?   ──→ Encoding / 自定义编码
    │
    ├── 图片含 QR/Barcode 视觉特征?    ──→ Misc Others / Brainteaser
    │
    └── 都不匹配?                  ──→ 共享基础（file + strings + binwalk）
```

**识别优先级**：
1. `python-magic` 检测 MIME（**优先**，per [`tools.md §4 python-magic-bin`](./tools.md)）
2. 文件后缀（兜底）
3. 内容嗅探（识别编码文本 / QR 视觉）
4. 全部失败 → 共享基础入口

详细实现见 [`Architecture.md §3.2 入口分流器`](./Architecture.md)。

---

## 7. 可疑点格式（统一 schema）

> **所有工具的输出统一通过 `SuspiciousPoint` dataclass 表达，GUI 高亮 + journal 记录都基于此**。

```python
@dataclass
class SuspiciousPoint:
    id: str                  # UUID，自动生成
    tool_name: str           # 触发的工具（如 "binwalk"）
    file_path: str           # 原始文件路径
    category: str            # 分类：flag / webshell / encoded / file_header / keyword / ...
    offset: int | None       # 字节偏移（None = 不适用）
    matched_pattern: str     # 匹配到的原始 pattern（如 "PK\x03\x04" / "uid=0" / "eval(base64_decode(...))"）
    context: str             # 周围上下文（前后 32 字节 hex + ASCII）
    severity: int            # 1-5（1=提示 / 3=可疑 / 5=强烈可疑）
    suggested_action: str    # 推荐下一步动作（"建议 foremost 分离" / "建议 base64 解码"）
    timestamp: datetime      # 触发时间
```

**category 关键字集合**（v0.1 初始）：
- `flag` — `flag{...}` / `ctf{...}` / `key{...}` 正则命中
- `webshell_family` — 冰蝎 / 菜刀 / 哥斯拉 / 变种 payload 特征
- `file_header` — PK / Rar / 7z / jpg / png / pdf 等 magic bytes
- `base64_candidate` — 长度 ≥ 16 且字符集匹配的 base64 串
- `base32_candidate` — 同上
- `hex_string` — 长度 ≥ 16 的纯 hex 串
- `keyword` — password / secret / hidden / encrypt 等敏感关键字
- `suspicious_url` — http:// / https:// 长 URL 含 webshell 关键字

---

## 8. 完成判定

> automisc 的"完成"**不追求 flag 匹配**（per `AGENTS.md §1` 铁律 4 备注）。

### 8.1 单次工具调用的成功标准

- ✅ subprocess 退出码 0（或工具自身的"成功"返回）
- ✅ 输出被正确解析为 `ToolResult`
- ✅ 可疑点列表非空（如果有匹配的 pattern）或 显式标注"无可疑点"
- ✅ journal 写入成功

### 8.2 单任务完成（per `AGENTS.md §1` 铁律 4）

1. ✅ 代码合并 main
2. ✅ `pytest -m "not integration"` 全绿
3. ✅ 涉及 GUI：`pytest -m integration` 跑通拖拽 / 菜单触发
4. ✅ 涉及工具调用：至少 1 个真实 misc 样本 smoke，journal 关键可疑点命中一致
5. ✅ Owner 自审
6. ✅ 文档同步

### 8.3 automisc v0.1 GA 标准

- ✅ §4.1 v0.1 任务看板全部 ✅
- ✅ §5.1 P0 工具池至少 5 个 adapter 跑通
- ✅ §6 入口分流表全部覆盖
- ✅ §7 可疑点 schema 在所有 adapter 统一
- ✅ journal 自动记录 + 导出功能可用
- ✅ 在至少 3 个真实 misc 样本上完整跑通（图片 / 流量 / 压缩各 1）

---

## 9. GUI 形态

### 9.1 主窗口布局（占位 · 待 Q3 决策）

**默认建议**：单窗口（左侧菜单树 + 右侧输出区 + 底部 journal 标签页）

```
┌────────────────────────────────────────────────────┐
│  [文件] [编辑] [工具] [视图] [帮助]                │  ← 菜单栏
├──────────┬─────────────────────────────────────────┤
│ 📁 隐写  │  工具输出区（实时滚动 + ANSI 高亮）      │
│ 📡 流量  │                                         │
│ 📦 压缩  │  [+] binwalk -e challenge.bin           │
│ 💾 内存  │  DECIMAL  HEXADECIMAL  DESCRIPTION       │
│ 🔐 编码  │  0        0x0          PNG image, ...   │
│ 🔍 取证  │  1024     0x400        Zip archive ...  │
│          │  ...                                    │
│ ─────────│                                         │
│ 📋 自动  │  [?] 可疑点：检测到 PK 文件头，建议 foremost│  ← 高亮
│   分析  │  [?] 可疑点：识别到 base64 串 ...           │
├──────────┴─────────────────────────────────────────┤
│ [输出] [Journal] [可疑点列表] [工具历史]            │  ← 底部标签页
└────────────────────────────────────────────────────┘
```

### 9.2 交互约定

- **拖拽接收**：单文件 / 多文件均可；拖入后自动触发入口分流，弹出 subflow 推荐菜单
- **菜单触发**：点击工具菜单项 → Core 调用 adapter → 输出区实时渲染
- **可疑点高亮**：所有 `SuspiciousPoint` 在输出区以醒目色块显示 + 底部"可疑点列表"标签页同步
- **journal 自动**：每次工具调用结束，自动追加一段到 journal 标签页
- **journal 导出**：菜单 → 文件 → 导出 journal → 保存为 `solve_journal.md`

### 9.3 macOS 集成（v0.5+ 候选）

- 文件拖拽到 Dock 图标直接进 automisc（需 `Info.plist` 配置）
- 工具完成时 macOS 通知中心提示
- Touch Bar 快捷触发（如果机器支持）

---

## 10. 演进路线图

```
v0.1（当前）              v0.5（中期）              v1.0（远期）
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ GUI + 工具池      │     │ + 工具链模板       │     │ + DAG 编排        │
│ + 手动菜单触发    │ ──→ │ （固定编排规则）    │ ──→ │ （基于数据依赖）   │
│ + 可疑点高亮      │     │ pcap/image/archive│     │ 可视化编排视图     │
│ + journal        │     │ 等预设模板          │     │ 手动干预 + 自动    │
└──────────────────┘     └──────────────────┘     └──────────────────┘
   纯离线                  纯离线                    纯离线
   macOS only              macOS only                macOS only
```

### 10.1 v0.1（当前 · 最小可用 GUI）

- 目标：手动菜单触发 + 可疑点高亮 + journal
- 工具池：5+ P0 adapter
- 编排：纯手动
- 完成：§4.1 全部任务 ✅

### 10.2 v0.5（中期 · 模板编排）

- 目标：固定编排模板（3 个预设）
- 工具池：P0 + P1 全部覆盖
- 编排：模板顺序执行
- 完成：§4.2 全部任务 ✅
- **不引入**：LLM / 云端 / 跨平台

### 10.3 v1.0（远期 · DAG 编排）

- 目标：基于数据依赖的 DAG 自动编排
- 编排：DAG 引擎 + 可视化视图 + 手动干预
- 完成：§4.3 全部任务 ✅
- **不引入**：LLM / 云端 / 跨平台

### 10.4 明确不演进的方向

| ❌ 不做 | 原因 |
|---|---|
| **不引入 LLM 编排决策** | 完全离线产品（per §2.2 硬约束）|
| **不桥接 `misc/skills/*SKILL.md`** | skill 是给 AI Agent 用的，automisc 不消费（per `Architecture.md §5`）|
| **不做跨平台** | macOS only |
| **不做云端同步 / Web UI / 远程服务** | 完全离线桌面工具 |
| **不做全自动拿 flag** | 半自动化辅助，最终决策权在人 |

---

## 11. 治理变更流程

本文件的修改需要：

1. **Owner 起草**变更提案
2. 在 PR 描述中写明 **"治理变更"** + 原因 + 影响范围
3. Owner 自审（单 Owner 项目）
4. 重要变更应同步更新 [`Architecture.md`](./Architecture.md)
5. 治理变更记录保留在 [`AGENTS.md §8`](./AGENTS.md) 变更日志

> 任何修改需求的请求 → 走本文档更新流程 → 再实施代码。

---

## 12. 变更日志

> **维护策略**：本表只保留**最近 4 条**。超出范围旧条目归档到 `docs/changelog/prd.md_archived.md`（v0.1+ 创建）。

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-13 15:13 | **1.2** | **v0.1.0b-PR9 实施完成**：包基座 smoke 验证（`pip install -e ".[dev]"` + `python -m automisc` + console_script 全跑通）。§4.1 PR9 状态 ⏳ → ✅。详见本次 commit。 |
| 2026-06-13 14:00 | **1.1** | **v0.1.0b-cleanup 治理重整**：① §4.1 合并两套任务体系（旧 `v0.1.0~v0.1.10` + 新 `v0.1.0b~PR9`）为单一 `v0.1.0b-*` 体系；② 按"依赖 + 价值 + 阻塞面"重排 P0~P9 优先级（cleanup → PR9 → PR3/4/5/6/8 → PR7-envfix+PR7 → encoders → GUI）；③ 新增"决策记录"小节说明排序理由；④ 移除旧编号任务行。详见本次 commit。 |
| 2026-06-13 | 1.0 | 初版：产品定位 + 用户故事 + 任务看板（v0.1/v0.5/v1.0）+ 工具池 + 入口分流表 + 可疑点 schema + 完成判定 + GUI + 演进路线图。详见 git history（commit 9401f98）。 |

---

> **最后一条**：
> 本文档是 automisc 的**需求 + 演进**单一事实来源。任何"今天起要做什么"问题先查这里。
> 历史决策在 [`AGENTS.md §8`](./AGENTS.md) + `git log`（永不删除）。