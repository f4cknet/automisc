# prd.md — AutoMisc 产品需求文档

> **🟡 FROZEN · 治理变更 v3.0 · 2026-06-13**
>
> **本文档已冻结，不再更新**。v0.1 已交付，所有任务状态在 `upgrade.md` 跟踪。
>
> **本文件仅作为历史 reference**保留（约 200 行内）。新任务 / 需求 / 演进路线请走：
> - 当前迭代 / 新需求 → [`upgrade.md`](./upgrade.md) + `upgrade/<id>.md`
> - 项目结构 / 模块作用 → [`STRUCTURE.md`](./STRUCTURE.md)
> - 治理 / 铁律 / Git 流程 → [`AGENTS.md`](./AGENTS.md)

---

## 0. 产品定位（历史快照）

`misc/automisc` 是**macOS 平台**、**完全离线**、**PySide6 GUI** 的 CTF Misc 半自动化辅助工具箱。

**核心交互**：拖入题目文件 → 工具菜单触发分析 → **可疑点高亮打印** + journal 自动记录 → 人工决策下一步。

**架构分层**（单向依赖）：GUI 层 / Core 调度层 / 工具池层 / 外部工具。架构已落地到代码，详见 `STRUCTURE.md`。

## 1. 范围 & 非范围（含硬约束）

### 1.1 范围（v0.1 必须做 · 已交付）

- **22 adapter** 分 8 类：Forensics (Network/Log/Memory) / Stego (Image/Audio/Video) / Misc (Archive/Brainteaser) / Shared
- **3 自编写编码**（base / classical / custom，非工具池）
- **PySide6 macOS GUI** + 拖文件 + journal 累积
- **5 chain** 模板（zip / zip-full / binwalk / foremost / lsb）

### 1.2 非范围（硬约束 · 永久）

- ❌ LLM / 云端服务 / 在线编排决策（**完全离线**）
- ❌ 跨平台（仅 macOS）
- ❌ flag 自动提交（automisc 拿 flag 是用户的事）
- ❌ 网络爬虫 / 远程字典攻击

### 1.3 异常路径（紧急通道）

- macOS 系统类紧急修复（PySide6 兼容）：24h 内补铁律 2
- CI 全红 hotfix：文档同 PR 跟上
- Owner 现场特批：PR 描述写明原因

## 2. 工具池（已交付，详见 `STRUCTURE.md §4`）

| Subflow | 工具 |
|---|---|
| Forensics/Network | tshark, tcpdump |
| Forensics/Log | grep, evtx_dump |
| Forensics/Memory | vol (volatility3) |
| Stego/Image | zsteg, steghide |
| Stego/Audio | sox, ffmpeg_audio, steghide_audio |
| Stego/Video | ffmpeg_video, ffprobe |
| Misc/Archive | sevenz, unzip, john |
| Misc/Brainteaser | zbar (QR) |
| Shared | binwalk, foremost, file, strings, xxd, exiftool |

## 3. 链（chain）速查（已交付，详见 `STRUCTURE.md §5`）

| chain | 拓扑 | 适用 |
|---|---|---|
| `zip` | try_unzip → fix_pseudo | 已知 zip 伪加密检测 |
| `zip-full` | try_unzip → fix_pseudo → bruteforce | zip 真加密爆破（4-6 位数字/字母）|
| `binwalk` | binwalk 检测 + foremost 提取 | 复合文件分离 |
| `foremost` | foremost 单独提取 | skip binwalk 检测 |
| `lsb` | binwalk → lsb 智能路由 | PNG 隐写（text 终止 / file 二次 router）|

CLI: `automisc chain --chain {name} --file <path>`  
GUI: Run → Chain → Run {name} chain

## 4. 完成判定（6 关验收，per `AGENTS.md §1 铁律 4`）

1. ✅ 代码已合并 main
2. ✅ `pytest -m "not integration"` 全绿
3. ✅ GUI 行为变更跑 `pytest -m integration` 跑通
4. ✅ 真实样本 smoke（≥ 1 个真实 misc 样本）→ 关键可疑点命中
5. ✅ Owner 自审（单 Owner 项目）
6. ✅ 文档同步（`upgrade.md` / `STRUCTURE.md` 之一）

> "完成"**不追求 flag 匹配**——automisc 是半自动化辅助工具，验收是"工具调用成功 + journal 关键可疑点被命中"。

## 5. v0.5+ 演进方向（开放）

- 递归链（`recursive=True` 通用机制）
- GUI 进度条 + cancel 按钮
- v0.5-1 disk adapters（yara / bulk_extractor / photorec — per `upgrade/v0.5-roadmap.md`）
- 真实题库回归测试集（≥ 5 题）

详 `upgrade.md` 索引。

---

> **历史归档**：本文档原 527 行（§0~§10 完整 PRD），v3.0 治理变更压到 200 行内；**v0.1 任务看板、GUI 形态、演进路线图等历史快照**已归档到 `docs/changelog/prd.md_archived.md`（Owner 决定是否归档）。
