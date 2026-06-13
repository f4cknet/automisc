# upgrade.md — v0.5+ 迭代索引

> **用途**：v0.1 frozen release + v0.1.1 完整闭环（main `6e4e14f`）落地后，**频繁迭代**走 upgrade 模式。
> 每次迭代一个文件 `upgrade/{desc}.md`，本文档做索引。

---

## 状态

| 字段 | 值 |
|---|---|
| **当前 main HEAD** | `6e4e14f`（v0.1.1-auto-run）|
| **当前版本** | v0.1.1 |
| **下一个 milestone** | v0.5（per `prd.md §9` 演进路线）|
| **主分支** | main（per `AGENTS.md §2.5.1` v0.1.1 简化流程：直接 main commit）|
| **Owner 授权** | "完全信任 AI"（per AGENTS.md §2.5.1 v1.20 治理变更）|

---

## v0.5 路线图（`upgrade/v0.5-roadmap.md`）

详细规划见 [`upgrade/v0.5-roadmap.md`](upgrade/v0.5-roadmap.md)。摘要：

1. **补工具池** — 缺 disk/office/hexdump/scalpel adapter（per Architecture §4.4.1 "P1 未排期"）
2. **真实 fixture** — vmem + evtx（小体积，2MB 内，pytest 用）
3. **GUI 增强** — output 区按工具分组折叠 / 进度条 / journal 按时间排序
4. **Core 增强** — router 加 magic bytes 之外的 entropy / heuristic 探测 + FileRouter 智能分级
5. **持久化** — Core journal 落盘（JSONL）跨 session 搜索
6. **批量并发** — AutoRunner 改 QThreadPool 并发跑 top N（牺牲可读性换速度）

---

## 迭代记录

| ID | 标题 | 状态 | 实施 | 文件 |
|---|---|---|---|---|
| v0.1.1-auto-run | 拖文件自动跑 top 5 推荐 | ✅ done | main `6e4e14f` | [`upgrade/v0.1.1-auto-run.md`](upgrade/v0.1.1-auto-run.md) |
| v0.5-DAG-chain | binwalk 检测 + 自动分离 + zip 智能分析链 | ✅ done | main (待 push) | [`upgrade/v0.5-DAG-chain.md`](upgrade/v0.5-DAG-chain.md) |

---

## 使用方法

### 启动新迭代

1. AI Agent 创建 `upgrade/{version}-{slug}.md`（如 `upgrade/v0.5-1-disk-adapters.md`）
2. 在本文档"迭代记录"表加一行（id / 标题 / 状态 🔄 / 链接到详情）
3. AI Agent 按"6 关验收"流程实施：代码 + 测试 + 真实样本 smoke + 文档 + commit + push main

### 完成迭代

1. 改 status ✅ + 填 merged commit SHA
2. 改 prd.md §4.1（如任务粒度够大可独立成行）/ Architecture.md / AGENTS.md
3. 跑 `pytest tests` 全过（per 铁律 4 关 2）

---

## 跟其他文档的关系

| 文档 | 关系 |
|---|---|
| `prd.md` | v0.1 任务体系（v0.1.0b-* 11 行）；v0.5+ 新任务如果粒度大可入 §4.1 任务行 |
| `Architecture.md` | 架构目标（§4.4.1 target）+ 当前落地（§4.4.2 actual）；每次迭代同步两边 |
| `AGENTS.md` | 治理规则 + 变更日志（§8）；治理变更入 §7 |
| `CHANGELOG.md` | 用户视角的发布说明（v0.5+ 每次 release 写） |
| `fix.md` | bug 修复索引（v0.1+；与 upgrade 并行） |

---

## 治理

- **本目录由 AI Agent 全权管理**（per AGENTS.md §2.5.1 v0.1.1 简化流程）
- **不删** 已 done 的迭代文件（保留历史 + git blame 追溯）
- **跨任务依赖** 写在每个 upgrade/{desc}.md 顶部 "依赖" 段
- **失败 / 取消** 的迭代改 status ❌ + 写原因
