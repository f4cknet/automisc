# upgrade.md — v0.5+ 迭代索引

> **用途**：v0.1 frozen release + v0.1.1 完整闭环（main `6e4e14f`）落地后，**频繁迭代**走 upgrade 模式。
> 每次迭代一个文件 `upgrade/{desc}.md`，本文档做索引。

---

## 状态（snapshot · 2026-06-13 23:23 · 收官）

| 字段 | 值 |
|---|---|
| **当前 main HEAD** | `e2fe29c`（v0.5-session-summary）|
| **当前版本** | v0.5+（频繁迭代模式，已 9 迭代）|
| **下一个 milestone** | 待 Owner 决策（**3 个新工具** base64 data URL / JPEG trailer / QR 坐标 4-5h，**优先**）|
| **主分支** | main（per `AGENTS.md §2.4` 单 Owner 简化：直接 main commit）|
| **Owner 授权** | "完全信任 AI"（per AGENTS.md §2.4 v1.20 治理变更）|
| **3 件套行数** | AGENTS 101 + prd 93 + STRUCTURE 186 = **380 行**（v3.0 治理）|
| **测试** | **349 passed**（306 v0.1.1 基线 + 43 v0.5+ 增量）|
| **真 flag 数** | **4**（QR + steg + KEY + meihuai）|
| **今晚 commit 数** | 8 (4b4af51 → b9226c1) |
| **真 flag 命中** | 2 (Challenge/QR_code.png `CTF{vjpw_wnoei}` + Challenge/steg.png `st3g0_saurus_wr3cks`) |

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
| v0.5-DAG-chain | binwalk 检测 + 自动分离 + zip 智能分析链 | ✅ done | main `31fe17a` | [`upgrade/v0.5-DAG-chain.md`](upgrade/v0.5-DAG-chain.md) |
| v0.5-DAG-chain-realtest | CLI 实测 Challenge/QR_code.png 拿 flag `CTF{vjpw_wnoei}` | ✅ done | main `e2b9587` | [`upgrade/v0.5-DAG-chain-realtest.md`](upgrade/v0.5-DAG-chain-realtest.md) |
| v0.5-DAG-chain-refactor | foremost 工具模块化（binwalk delegate to foremost） | ✅ done | main `4b4af51` | [`upgrade/v0.5-DAG-chain-refactor.md`](upgrade/v0.5-DAG-chain-refactor.md) |
| v0.5-DAG-stress-test | 6 道压力测试（伪加密/真加密/foremost/套娃/多嵌/纯 png） | ✅ done | main `c3617f1` | [`upgrade/v0.5-DAG-stress-test.md`](upgrade/v0.5-DAG-stress-test.md) |
| v0.5-LSB-router | LSB 抽取后智能路由（text 终止 / file 二次 router） | ✅ done | main `bdb0b4e` | [`upgrade/v0.5-LSB-router.md`](upgrade/v0.5-LSB-router.md) |
| v0.5-LSB-router-GUI | Chain 菜单 + 5 chain GUI 入口同步 CLI | ✅ done | main `6597842` | [`upgrade/v0.5-LSB-router.md`](upgrade/v0.5-LSB-router.md)（同文件）|
| v0.5-gui-zip-full | GUI `_maybe_trigger_zip_chain_from_binwalk` 走 zip-full (bug 修) | ✅ done | main `1cf4850` | [`fix_gui_zip_trigger_no_bruteforce.md`](../fix_gui_zip_trigger_no_bruteforce.md) |
| governance-v2.0 | 删 Architecture.md + prd.md frozen + 新建 STRUCTURE.md | ✅ done | main `895f54e` | [`STRUCTURE.md`](../STRUCTURE.md) |
| governance-v3.0 | AGENTS.md + prd.md 压到 200 行内 | ✅ done | main `0daeaac` | [`AGENTS.md`](../AGENTS.md) |
| v0.5-GUI-shortcuts | 工具栏 4 快捷入口: lsb / fix_pseudo / bruteforce_zip / bruteforce_rar | ✅ done | main `b9226c1` | [`upgrade/v0.5-session-summary-2026-06-13.md`](upgrade/v0.5-session-summary-2026-06-13.md) |
| v0.5-lsb-bug | 修 LSBExtractAction 抽 raw 含 0xff 抛 UnicodeDecodeError | ✅ done | main `f1a55ca` | [`upgrade/2026-06-14-new-fixtures.md`](upgrade/2026-06-14-new-fixtures.md) |
| v0.5-base64-image | base64 -> 图片工具 (CLI `automisc decode base64-image`) | ✅ done | main `100189c` | [`upgrade/v0.5-base64-image.md`](upgrade/v0.5-base64-image.md) |
| v0.5-rule-scanner | rule_scanner 独立规则库 + strings|grep 集成 + auto_run 兜底 | ✅ done | main `4573369` | [`upgrade/v0.5-rule-scanner.md`](upgrade/v0.5-rule-scanner.md) |
| v0.5-decoder-menu | CLI decoder 迁移到 GUI Tools 菜单 (registry 单一事实来源) | ✅ done | main `9e9002d` | [`upgrade/v0.5-decoder-menu.md`](upgrade/v0.5-decoder-menu.md) |
| v0.5-GUI-bugfix | 3 bug 修: 工具栏 base64/hex 入口 + LSB secret/key 高亮 | ✅ done | main (待 push) | [`upgrade/v0.5-GUI-bugfix.md`](upgrade/v0.5-GUI-bugfix.md) |

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
