# upgrade.md — v0.5+ 迭代索引

> **用途**：v0.1 frozen release + v0.1.1 完整闭环（main `6e4e14f`）落地后，**频繁迭代**走 upgrade 模式。
> 每次迭代一个文件 `upgrade/{desc}.md`，本文档做索引。

---

## 状态（snapshot · 2026-06-14 17:50 · v0.5-base-rot-decoders 完工）

| 字段 | 值 |
|---|---|
| **当前 main HEAD** | `e2fe29c`（v0.5-session-summary，**未推新 commit**）|
| **当前版本** | v0.5+（频繁迭代模式，已 13 迭代）|
| **下一个 milestone** | **v0.5-base-rot-decoders**（PR1+PR2+PR3 全完工，**等 Owner 自审后 commit + push**）|
| **主分支** | main（per `AGENTS.md §2.4` 单 Owner 简化：直接 main commit）|
| **Owner 授权** | "完全信任 AI"（per AGENTS.md §2.4 v1.20 治理变更）|
| **3 件套行数** | AGENTS 101 + prd 93 + STRUCTURE 186 = **380 行**（v3.0 治理）|
| **测试** | **592 passed**（v0.5-base-rot-decoders +24 单测：PR1 算法库 37 + PR2 base64 stego 15 + PR3 decoder+GUI 24）— 4 failed 跟本次无关（Challenge 文件缺失 + 包安装）|
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
| v0.5-GUI-bugfix | 3 bug 修: 工具栏 base64/hex 入口 + LSB secret/key 高亮 | ✅ done | main `879738f` | [`upgrade/v0.5-GUI-bugfix.md`](upgrade/v0.5-GUI-bugfix.md) |
| v0.5-IO-widget | OutputView → InputOutputView (Clear/Paste/Hex→ASCII 4 按钮) | ✅ done | main `7a61aa5` | [`upgrade/v0.5-IO-widget.md`](upgrade/v0.5-IO-widget.md) |
| v0.5-output-samedir | 所有文件输出都跟 input 同目录 (不再写 /tmp) | ✅ done | main `af35fb0` | [`upgrade/v0.5-output-samedir.md`](upgrade/v0.5-output-samedir.md) |
| v0.5-hex-ascii-fix + v0.5-clear-on-new-file | 删顶 bar 按钮 + hex-ascii 走 input + 拖新文件清空旧 output | ✅ done | main `aed9bb1` | [`upgrade/v0.5-hex-ascii-fix.md`](upgrade/v0.5-hex-ascii-fix.md) |
| v0.5-coords-qr | 坐标串 → QR PNG → zbar (菜单栏新增 🔳 QR 工具 分类) | ✅ done | main `ea70001` | [`upgrade/v0.5-coords-qr.md`](upgrade/v0.5-coords-qr.md) |
| v0.5-truncate-output + v0.5-short-circuit | strings/grep 渲染版 stdout (不打印 raw) + AutoRunner 命中 severity>=5 终止链 | ✅ done | main `386e3c0` | [`upgrade/v0.5-truncate-output.md`](upgrade/v0.5-truncate-output.md) |
| v0.5-tmp-text-mode | text 模式 (无 file_path) 写 /tmp + GUI 弹 QFileDialog 选 dir | ✅ done | main `abf2ff4` | [`upgrade/v0.5-tmp-text-mode.md`](upgrade/v0.5-tmp-text-mode.md) |
| v0.5-tmp-text-mode-2 | QFileDialog 只在 decoder 真写文件时弹 (hex-ascii 不弹) | ✅ done | main `94794c9` | [`upgrade/v0.5-dialog-when-write-file.md`](upgrade/v0.5-dialog-when-write-file.md) |
| v0.5-hex-router | strings 命中长 hex (>=200 chars) 自动探测 magic + 写 /tmp + 调 zbar/unzip; 短 hex 仍打印 | ✅ done | main (待 push) | [`upgrade/v0.5-hex-router.md`](upgrade/v0.5-hex-router.md) |
| v0.5-tool-install-batch-1 | 装 5 个 tools.md ❌ 工具 (pcapfix/compiled + aircrack-ng + scapy + impacket + python-evtx)，更新 tools.md 状态；意外发现 evtx_dump CLI shim 坏，待 fix | 🔄 in-progress | (无 commit，无代码改动) | [`upgrade/v0.5-tool-install-batch-1.md`](upgrade/v0.5-tool-install-batch-1.md) |
| v0.5-tool-install-batch-2 | sox brew 装 (❌→✅) + evtx_dump 走 extend_tools/ Rust 0.8.2 (⚠️→✅，跟 python-evtx 不同项目) + python-evtx (⚠️→✅) | ✅ done | (无 commit，无代码改动) | [`upgrade/v0.5-tool-install-batch-2.md`](upgrade/v0.5-tool-install-batch-2.md) |
| v0.5-base-rot-decoders | base 家族 (36/92/100/32768/65536 + 自定义表) + rot 家族 (5/47/18) + base64 stego 解码封装 → "🔐 Base/ROT 解码" GUI 二级分类 (18 decoder 扁平) | ✅ done | (3 PR 完工：PR1 算法库 92 单测, PR2 base64 stego 15 单测, PR3 decoder + GUI 19+5 单测；总 +24 单测 568→592 passed) | [`upgrade/v0.5-base-rot-decoders.md`](upgrade/v0.5-base-rot-decoders.md) |
| v0.5-cipher-decoders | 12 个经典 cipher (凯撒/培根/栅栏/猪圈/摩尔斯/xxencode/uuencode/jsfuck/jjencode/QP/BF/BubbleBabble) → "🔤 解密工具1" 一级目录 + "占位 — TBD" 入口放 解密工具2/3 | ✅ done | (1 commit；+54 单测 592→646 passed；DecoderSpec 加 group 字段 + list_decoders_by_group + GUI _build_tools_menu 双重渲染 group→category) | [`upgrade/v0.5-cipher-decoders.md`](upgrade/v0.5-cipher-decoders.md) |
| v0.5-cipher-decoders-textfix | text_only 自动声明, 28 个 decoder 走 input 区 (v0.5-cipher-decoders §9) | ✅ done | (1 commit；+8 单测 646→657 passed；DecoderSpec.text_only 字段 + 28 个 decoder 注册时声明 True + GUI _run_decoder 改读 spec.text_only 标志代替硬编码 list) | [`upgrade/v0.5-cipher-decoders.md`](upgrade/v0.5-cipher-decoders.md) |
| v0.5-cipher-decoders-wordsep | morse --word-sep 参数, CTF 数字串拼成连续字符串 (v0.5-cipher-decoders §10) | ✅ done | (1 commit；+4 单测 657→669 passed；morse_decode 加 word_sep 参数 + CLI --word-sep + Owner 真样本 '5BC925649CB0188F52E617D70929191C') | [`upgrade/v0.5-cipher-decoders.md`](upgrade/v0.5-cipher-decoders.md) |
| v0.5-more-converts + v0.5-zbar-rename | 6 个新进制转换 (bin-ascii / dec-bin / bin-dec / dec-hex / hex-dec / ascii-bin) + zbar 改名为"🔳 二维码解析" | ✅ done | (1 commit；+72 单测 669→741 passed；ZBAR_DISPLAY_NAME 常量 + hex-dec 修 _strip_text bug) | [`upgrade/v0.5-more-converts.md`](upgrade/v0.5-more-converts.md) |
| v0.5-pcap-protocol-router | pcap 协议层路由：协议分类（TLS 加密 vs FTP/SMTP 明文）+ key 候选发现（.key/.pub/.pem）+ **不**自动解密 + 输出 Wireshark 手动命令模板；触发题：Challenge/greatescape.pcap | 🟡 design | (无 commit，待 Owner 拍板 §7 决策点后走铁律 2) | [`upgrade/v0.5-pcap-protocol-router.md`](upgrade/v0.5-pcap-protocol-router.md) |
| v0.5-binwalk-extract | binwalk adapter 补 PEM/SSH/RSA 私钥关键字 + 自动 `binwalk -e` 提取到 samedir + SuspiciousPoint context 显示提取路径；推翻"binwalk macOS 兼容性问题"旧定论（bug 在 adapter 层不在 CLI）；同 greatescape.pcap 暴露姊妹 bug | 🟡 design | (无 commit，实施中) | [`upgrade/v0.5-binwalk-extract.md`](upgrade/v0.5-binwalk-extract.md) |
| v0.5-train-002-zip-pseudo-175b | **训练驱动第 2 篇**：175B zip 伪加密（`flag{Adm1N-B2G-kU-SZIP}`），暴露 GUI 工具栏 fix_pseudo_zip 按钮 vs CLI `chain --chain zip` 行为不一致 UX bug；触发 §5.2 架构升级 `v0.5-zip-toolbar-routing`（待建）| ✅ done | (无 commit，纯训练日志；fixtures 归档 zip_pseudo_175b.zip) | [`upgrade/v0.5-train-002-zip-pseudo-175b.md`](upgrade/v0.5-train-002-zip-pseudo-175b.md) |
| v0.5-train-003-jpeg-zip-deadlock | **训练驱动第 3 篇**：JPEG 1366x768 嵌加密 zip @ offset 68019（真加密密码未知，Owner 跳过爆破授权）；Owner 报"auto-run 卡住"——**根因 GUI 主线程同步调 dag.execute 跑 zip-full chain 8.4M 字典 brutalforce 永远跑不完**；触发 §5.2 架构升级 `v0.5-auto-run-async-chain`（待建）| 🚧 in-progress | (无 commit，纯训练日志) | [`upgrade/v0.5-train-003-jpeg-zip-deadlock.md`](upgrade/v0.5-train-003-jpeg-zip-deadlock.md) |
| v0.5-train-004-cdh-pseudo-detect | **训练驱动第 4 篇**：`Challenge/123456cry.jpg` foremost 雕的 `00000038.zip` (29KB) 报"真加密"——**根因 `_is_pseudo_encrypted` 只扫 LFH bit0，漏识别「CDH 假加密」形态 B (LFH=0/CDH=1, owner 这题命中)**；zipfile/7z/unzip 读 CDH 判定加密，LFH/CDH 标志位不一致是标准实现层 bug；fix_pseudo 修复代码已对 LFH+CDH，**只升级检测即可**；详见 [`fix_zip_pseudo_cdh_detection.md`](../fix_zip_pseudo_cdh_detection.md) | 🚧 in-progress | (无 commit，代码 + 单测待实施) | [`upgrade/v0.5-train-004-cdh-pseudo-detect.md`](upgrade/v0.5-train-004-cdh-pseudo-detect.md) |
| v0.5-zip-pseudo-cdh-detect | **bug 修复**：`zip_chain._is_pseudo_encrypted` 升级同时扫 LFH + CDH 标志位，覆盖伪加密 3 形态 (A=LFH假 / B=CDH假 / C=双假)；`fix_pseudo` 修复代码不动 (已对 LFH+CDH)；加 3 形态 fixture + 6 单测；触发 `v0.5-train-004` | 🚧 in-progress | (无 commit，代码 + 单测待实施) | [`fix_zip_pseudo_cdh_detection.md`](../fix_zip_pseudo_cdh_detection.md) |
| v0.5-train-005-per-entry-classify | **训练驱动第 5 篇**：`00000038.zip` 部分伪加密 + 部分真加密 — **算法升级 per-entry 独立判断**, 抽 `_classify_zip_entries` 函数返回 `{pseudo, real, clear}`, `FixPseudoEncryptionAction` 只修 pseudo entry, 不修真加密 entry (per owner 决策 A). 详见 [`upgrade/v0.5-zip-pseudo-per-entry-classify.md`](upgrade/v0.5-zip-pseudo-per-entry-classify.md) | ✅ done | (代码 + 单测已实施 13/13 passed) | [`upgrade/v0.5-train-005-per-entry-classify.md`](upgrade/v0.5-train-005-per-entry-classify.md) |
| v0.5-zip-pseudo-per-entry-classify | **架构升级**：`_classify_zip_entries` 函数化 + per-entry 分类 + `fix_pseudo` 只修真加密 + verdict SP 4 种情形. **v0.5-train-006 延伸**: 弃用 `data[11] in range(12)` 启发式 (命中率仅 4.7%), 改用 `zlib.decompress + CRC-32 校验` 作客观判据. | ✅ done | (代码 + 3 新单测已实施 13/13 passed) | [`upgrade/v0.5-zip-pseudo-per-entry-classify.md`](upgrade/v0.5-zip-pseudo-per-entry-classify.md) |
| v0.5-train-006-zip-classify-byte11-bug | **训练驱动第 6 篇**：`00000000.zip` (QR_code.png foremost 雕) 报"纯伪加密"误导用户 — **根因 byte[11] in range(12) 启发式命中率仅 4.7%, 绝大多数真加密 zip 被错判成伪加密**. Owner 反馈"这个 zip 其实是真加密...这让我感觉很不可思议". 触发架构升级 `v0.5-zip-pseudo-per-entry-classify` 的 §2.4 算法重写. | ✅ done | (无 commit, 待 Owner 签字 push) | [`upgrade/v0.5-train-006-zip-classify-byte11-bug.md`](upgrade/v0.5-train-006-zip-classify-byte11-bug.md) |
| v0.5-train-007-empty-zip-crash | **训练驱动第 7 篇**: Owner 2026-06-20 17:05 反馈 zip_classify.py **空 ZIP 崩溃** (UnboundLocalError on verdict_summary) + 算法层 2 个边界风险 (data descriptor / 非 store-deflate method). **修**: else 兜底分支 + severity 1. **defer**: data descriptor + 非 store/deflate (按 §5.2 等实战命中再升架构). | ✅ done | (无 commit, 待 Owner 签字 push) | [`upgrade/v0.5-train-007-empty-zip-crash.md`](upgrade/v0.5-train-007-empty-zip-crash.md) |
| v0.5-train-008-lsb-text-write-file | **训练驱动第 8 篇**: Owner 2026-06-20 17:26 实测 `flag11.png` (LSB 隐写 17531B 垃圾 unicode) — `LSBExtractAction` text 分支只 print 不写文件, **漏 `output_path_for` 同目录写盘动作** (file 分支已对). 触发 `v0.5-LSB-router` UX 修复 (text 通道 main 也写文件). | ✅ done | (无 commit, 待 Owner 签字 push) | [`upgrade/v0.5-train-008-lsb-text-write-file.md`](upgrade/v0.5-train-008-lsb-text-write-file.md) |
| v0.5-keyword-variants | 实战累积加 3 keyword: **p@ssphrase / fl@g / s3cr3t** + 修老 bug: `rule_scanner._SENSITIVE_KEYWORDS` 跟 `suspicious.KEYWORDS` 不同步 (补 6 个: pass/f1ag/p@ssw0rd/p@ssphrase/fl@g/s3cr3t);keyword 白名单 8 → 11 (per Owner 2026-06-20 19:39) | 🔄 in-progress | (无 commit，待 push) | [`upgrade/v0.5-keyword-variants.md`](upgrade/v0.5-keyword-variants.md) |
| v0.5-sevenz-extract | **新建 `sevenz_extract` adapter** — 真正 `7z x` 解压 (zip/7z/rar/tar/vmdk/vhd/wim 等 30+ 格式) → GUI 工具栏 "Misc/Archive" 下加 "📦 7z 解压",跟 sevenz / unzip / john / zip_classify 同一级;不动现有 sevenz adapter (探测);per Owner 19:48 拍板 writeup 面具下的flag | 🔄 in-progress | (无 commit，待 push) | [`upgrade/v0.5-sevenz-extract.md`](upgrade/v0.5-sevenz-extract.md) |
| v0.5-sevenz-toolbar-cleanup | **GUI menu 清理**: sevenz (探测类) 从 `TOOL_CATEGORIES["Misc/Archive"]` + `ADAPTER_TOOLS` 移除,但 **保留 adapter** (auto_run / router / find_suspicious 还在用);新原则: "用于自动化探测的工具,可不显示在 GUI menu" (per Owner 20:03);跨项目 GUI menu 设计铁律 | 🔄 in-progress | (无 commit，待 push) | [`upgrade/v0.5-sevenz-toolbar-cleanup.md`](upgrade/v0.5-sevenz-toolbar-cleanup.md) |
| v0.5-decoder-arch-doc | **文档化架构**: `STRUCTURE.md` 新增 §3.5 "GUI 工具来源 (tools/ vs decoders/)" — 解 cipher 解密工具为啥在 `core/decoders/` 不在 `tools/` (adapter 调外部 CLI vs decoder 纯计算); `AGENTS.md` §0 加指针 (per Owner 20:40 拍板);**0 代码改动** | 🔄 in-progress | (无 commit，待 push) | [`upgrade/v0.5-decoder-arch-doc.md`](upgrade/v0.5-decoder-arch-doc.md) |
| v0.5-decoder-friendly-candidate | **extract_base_candidate 加 decoder-friendly 特例**: raw brainfuck / raw Ook! 代码 paste 到 input 区 算候选 (per Owner 21:17 实战 — GUI 之前报"input 区为空");不动 base64/hex/binary/caesar 现有判定 | 🔄 in-progress | (无 commit，待 push) | [`upgrade/v0.5-decoder-friendly-candidate.md`](upgrade/v0.5-decoder-friendly-candidate.md) |
| v0.5-decoder-friendly-hint | **paste 后智能 hint**: 新建 `content_detector.detect_input_intent` 检测 input 区内容类型 (Ook!/BF/base64/base32/hex/binary/caesar 7 规则), GUI paste_clipboard 末尾追加 hint 行 `💡 检测到 X, 推荐 🦧 Ook! 解密`;**不阻挡老手选择** (per Owner 21:25 选 Y = 方案 A);触发 Owner 实战 Ook! 跑 BF 误操作 | ✅ done | (1 commit; +29 单测; decoder 24 + GUI paste hint 5) | [`upgrade/v0.5-decoder-friendly-hint.md`](upgrade/v0.5-decoder-friendly-hint.md) |

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
