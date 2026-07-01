# STRUCTURE.md — automisc 项目结构速查

> **创建时间**：2026-06-13 22:53  
> **状态**：✅ done  
> **触发**：Owner 指出 `AGENTS.md` + `Architecture.md` + `prd.md` 三件套 1900+ 行，**架构已落地到代码**，文档冗余拖累 context  
> **治理变更**（per `AGENTS.md §7`）：本目录取代 `Architecture.md`；`AGENTS.md` 删 v1 架构章节；`prd.md` 冻结

---

## 1. 项目一句话

**macOS 平台**、**完全离线**、**PySide6 GUI** 的 CTF Misc 半自动化辅助工具箱。

- 拖文件 / 命令行 → 工具菜单触发 → **可疑点高亮打印** + journal 自动记录
- 人工决策下一步（automisc 是**半自动化**，不抢 flag）

---

## 2. 目录布局

```
automisc/
├── AGENTS.md                     治理 (铁律 + Git 流程 + fix 索引) — 每个 session 必读
├── STRUCTURE.md                  ← 本文件 (项目结构 + 文件作用)
├── README.md                     用户向介绍
├── pyproject.toml                Python 包配置 (PEP 621)
│
├── prd.md                        🟡 frozen — 历史需求 (v0.1 已交付, 不再更新)
├── upgrade.md                    迭代索引 (v0.5+ 主入口)
├── upgrade/                      每次迭代 1 个 .md (永久保留)
├── upgrade/fix_<bug_name>.md     单 fix 详细记录 (per 2026-06-28 治理: 在 upgrade/ 子目录, 跟迭代 spec 同级)
├── fix.md                        修复记录索引 (指向 upgrade/fix_*.md)
│
├── Challenge/                    真实 CTF 题目 (per topic, owner 提供)
├── tests/fixtures/               测试 fixture (伪加密 zip, 文本样本等)
│
├── src/automisc/                 ← 源码
│   ├── __main__.py               CLI 入口 (automisc / automisc-gui 命令)
│   ├── __init__.py
│   ├── core/                     调度层 (无 GUI 依赖)
│   │   ├── orchestrator.py       主调度 (route + run_tool + journal)
│   │   ├── router.py             入口分流 (ext + magic → 工具推荐)
│   │   ├── dag.py                DAG 编排 (Action/ActionResult/DAGNode/DAG)
│   │   ├── chains.py             5 chain 模板 (zip/zip-full/binwalk/foremost/lsb)
│   │   ├── actions/              DAG Action 节点
│   │   │   ├── binwalk_extract.py    binwalk 检测 + foremost 提取 (delegated)
│   │   │   ├── foremost_extract.py   独立 foremost 提取 (GUI/CLI 共享)
│   │   │   ├── zip_chain.py          try_unzip / fix_pseudo / bruteforce 3 步
│   │   │   └── lsb_extract.py        LSB 智能路由 (v0.5-LSB-router 核心)
│   │   ├── encoding_detector.py  text 分类 (Q1: 敏感词 + base64/binary/hex)
│   │   ├── encoders/             自编写编码 (base/classical/custom + base64_stego + base_custom, 非工具池)
│   │   ├── decoders/             纯计算 decoder (不调外部 CLI, 跟 tools/ adapter 对偶)
│   │   │   ├── cipher_decoders.py    12 cipher (凯撒/培根/栅栏/猪圈/摩尔斯/xxencode/uuencode/jsfuck/jjencode/QP/BrainFuck/BubbleBabble) → GUI "解密工具1"
│   │   │   ├── base_rot_decoders.py  18 base/rot (base16/32/.../65536 + rot5/13/18/47) → GUI "🔐 Base/ROT 解码"
│   │   │   ├── base_convert.py       8 进制转换 (bin-ascii / dec-bin / ...) → GUI "🔢 进制转换"
│   │   │   ├── base64_image.py       base64 → 图片 → GUI "🔓 Base64 → 图片"
│   │   │   ├── coords_to_qr.py       坐标串 → QR PNG → GUI "🔳 坐标 → 二维码"
│   │   │   └── registry.py           DecoderSpec + list_decoders_by_group/category
│   │   ├── exceptions.py         异常体系 (AutomiscError + 6 子类)
│   │   ├── journal.py            操作日志 (JSONL flush + filter/export)
│   │   ├── registry.py           工具注册表 (@register_tool 装饰器)
│   │   ├── result.py             ToolResult dataclass
│   │   └── suspicious.py         SuspiciousPoint dataclass + 关键字集
│   ├── gui/                      PySide6 GUI (macOS only)
│   │   ├── main_window.py        QMainWindow + 拖文件 + 5 菜单 (File/View/Run/Chain/Help)
│   │   ├── menu_dock.py          左侧 22 adapter 分类菜单
│   │   ├── output_view.py        中央输出 + 严重度颜色 + flag_candidate 高亮
│   │   ├── journal_panel.py      底部 journal 累积
│   │   ├── runner.py             ToolRunner (QThread 单工具异步)
│   │   ├── chain_runner.py       ChainRunner (QThread 链异步, v0.5)
│   │   └── auto_runner.py        AutoRunner (QThread top-5 推荐自动跑)
│   └── tools/                    工具池 (subprocess 包装 + 输出解析)
│       ├── base.py               ToolAdapter 抽象基类
│       ├── shared/               跨类型工具 (binwalk/file/foremost/strings/xxd/exiftool)
│       ├── forensics/            Forensics 类
│       │   ├── network/          tshark / tcpdump / pcap_protocol_router (v0.5-pcap-protocol-router)
│       │   ├── log/              grep / evtx_dump
│       │   └── memory/           vol (volatility3)
│       ├── steganography/        Stego 类
│       │   ├── image/            zsteg / steghide
│       │   ├── audio/            sox / ffmpeg_audio / steghide_audio
│       │   └── video/            ffmpeg_video / ffprobe
│           └── misc/                 Misc 类
│           ├── archive/          sevenz / sevenz_extract / unzip / john / zip_classify
│           └── brainteaser/      zbar (QR)
│
├── tests/
│   ├── conftest.py               全局: sys.path + adapter 注册
│   ├── unit/                     单测 (不依赖 GUI)
│   │   ├── core/                 core/* 单元测试 (22 adapter + 7 core 模块)
│   │   └── tools/                tools/* 单元测试
│   ├── integration/              集成测试
│   │   └── gui/                  pytest-qt (offscreen) GUI 集成
│   └── fixtures/                 测试 fixture 文件
│
├── docs/
│   ├── changelog/AGENTS.md_archived.md  旧版 AGENTS.md 归档
│   └── decisions/                重要技术决策记录
│       └── v0.1.0b-PR7-vol-environment.md
│
├── extend-tools/                  外部 binary + 自动下载脚本 (per v0.5-platform-extend-tools)
│   ├── bin/
│   │   ├── win-x64/               Windows binaries (不入 git, install.ps1 自动下)
│   │   │   ├── binwalk.exe
│   │   │   ├── exiftool.exe
│   │   │   ├── 7zr.exe
│   │   │   └── foremost.exe
│   │   └── macos/                 macOS 暂留空 (brew 优先, v0.5+ 评估)
│   ├── manifest.yaml              工具 URL + SHA256 + 版本 (入 git)
│   ├── install.ps1                Windows 自动下载脚本
│   ├── install.sh                 macOS 自动下载脚本 (暂留 stub)
│   ├── README.md                  工具状态 + Windows 限制说明
│   └── .gitignore                 bin/win-x64/* 不入 git
└── tools.md                      外部工具清单 (deprecated 冗余, 待清理)
```

---

## 3. 核心模块作用表

| 模块 | 作用 | 关键导出 |
|---|---|---|
| `core/orchestrator.py` | 主调度，桥接 router / adapter / journal | `CoreOrchestrator` |
| `core/router.py` | ext + magic 头 → 工具推荐 (top N) | `FileRouter`, `recommend_tools`, `detect_magic` |
| `core/dag.py` | Action 抽象 + DAGNode + DAG.execute | `Action`, `ActionResult`, `DAG`, `DAGNode` |
| `core/chains.py` | 6 chain 模板 builder (5 + v0.5-lsb-byte-stream-extract) | `build_zip_chain_dag`, `build_zip_chain_with_bruteforce`, `build_binwalk_extract_dag`, `build_foremost_extract_dag`, `build_lsb_extract_chain`, `build_lsb_bytes_chain` |
| `core/actions/binwalk_extract.py` | binwalk 检测 + 委托 foremost 提取 | `BinwalkExtractAction` |
| `core/actions/foremost_extract.py` | 独立 foremost 提取 + helper | `ForemostExtractAction`, `find_foremost_extract` |
| `core/actions/zip_chain.py` | try_unzip / fix_pseudo / bruteforce 3 Action | `TryUnzipAction`, `FixPseudoEncryptionAction`, `BruteforceZipAction` |
| `core/actions/lsb_extract.py` | LSB 抽取后智能路由 (zsteg-based, v0.5-LSB-router 核心); **v0.5-lsb-extract-output-bytes 修写真**: magic 判定后缀 (89 50 4E 47 = .png / 50 4B = .zip 等, 复用 `lsb_detect._detect_file_header_hex`) + `write_bytes` 写真二进制 (per Owner "用 python wb") + fallback `.bin` 默认; GUI 工具栏 "🎨 PNG LSB 智能提取" 入口调它 | `LSBExtractAction`, `_decide_suffix`, `_write_tmp_extracted` |
| `core/actions/lsb_bytes_extract.py` | **v0.5-lsb-byte-stream-extract 能力 B**: LSB 字节流自定义抽取 (PIL/numpy 直抽, 4 参数 user-controlled: channel × bit × scan_order × byte_bit_order) | `LSBBytesExtractAction` |
| `core/encoding_detector.py` | text 严重度评分 (Q1 决策) | `score_text_severity`, `has_sensitive_keyword` |
| `core/exceptions.py` | 异常体系 (单 Owner 简化: 1 基类 + 6 子类) | `AutomiscError` + 6 子类 |
| `core/journal.py` | 操作日志 (累积 + 过滤 + 导出 JSONL) | `Journal`, `JournalEntry` |
| `core/registry.py` | 工具注册 (单 Owner 简化) | `@register_tool`, `get_tool`, `list_tools` |
| `core/result.py` | 工具结果统一 schema | `ToolResult` |
| `core/suspicious.py` | 可疑点统一 schema + 关键字集 | `SuspiciousPoint`, `SUSPICIOUS_PATTERNS` |
| `core/encoders/` | 自编写编码 (base / classical / classical_ext / custom / base64_stego / base_custom) | — |
| `core/decoders/registry.py` | decoder 注册表 + group/category 双重渲染 | `DecoderSpec`, `register_decoder`, `list_decoders_by_category`, `list_decoders_by_group` |
| `core/decoders/base64_image.py` | base64 → 图片 decoder | `decode_file_to_image` |
| `core/decoders/base_convert.py` | hex/binary/64/32 → ASCII 转换 decoder | — |
| `core/decoders/base_rot_decoders.py` | 18 个 base/rot decoder 聚合注册 | — |
| `core/decoders/coords_to_qr.py` | 坐标串 → QR PNG → zbar decoder | — |
| `core/decoders/cipher_decoders.py` | 12 经典 cipher (凯撒/培根/栅栏/猪圈/摩尔斯/xxencode/uuencode/jsfuck/jjencode/QP/BF/BubbleBabble) + 2 占位 → 解密工具1/2/3 | `run_caesar`, `run_bacon`, ..., `run_bubblebabble`, `run_placeholder` |
| `core/decoders/magic_sniffer.py` | **v0.5-lsb-byte-stream-extract 能力 C**: 字节流 magic 嗅探 (滑动窗口扫 offset 0~32, 50+ 文件 magic: PNG/ZIP/Py2.x pyc/Py3.x pyc/JPEG/ELF/WASM/Mach-O/Java/...), 解决 `router.detect_magic` 只看 offset 0 痛点 | `sniff_magic`, `run_magic_sniffer`, `EXTENDED_MAGIC_SIGNATURES` |
| `core/decoders/pyc_decompiler.py` | **v0.5-pyc-magic-sniffer 能力 E + v0.5-pyc-decompiler-buttons 扩展 + v0.5-pyc-decompiler-pycdc 主路径**: Py2.x / Py3.x .pyc 文件反编译到 Python 源码 (Py2.x 优先 **pycdc C++ 反编译器** → uncompyle6 + fix_uncompyle6_consts_bug fallback → dis fallback; Py3.x 走 decompyle3 → dis fallback), 输入 .pyc 路径 → 输出 source_code + 元数据 (magic_int / version / force_version / output_path); `force_version` 参数 (None=auto/2=py2/3=py3) 路由强制版本, 成功反编译时写 `<stem>__pyc[_pyN].py` 到 pyc 同目录 (per v0.5-output-samedir) | `run_pyc_decompiler`, `PycDecompileResult`, `_decompile_with_pycdc`, `_decompile_with_uncompyle6`, `_decompile_with_decompyle3`, `_decompile_with_dis`, `_fix_uncompyle6_consts_bug`, `_purpose_for_force` |
| `gui/main_window.py` | QMainWindow + 5 菜单 + 拖文件 | `MainWindow` |
| `gui/chain_runner.py` | 链 QThread (v0.5) | `ChainRunner` |

---

## 3.5 GUI 工具来源说明 — tools/ vs decoders/ (per Owner 20:40 拍板)

> **背景**: Owner 看到 GUI 菜单有 "解密工具1" 分类 (凯撒/培根/栅栏/.../BrainFuck/BubbleBabble 等 11 cipher),
> 但 `src/automisc/tools/` 下没对应目录, 误以为后端缺实现.
>
> **真相**: GUI 工具栏有 **两种来源**, 不是所有 GUI 工具都在 `tools/`.

### 架构对比

| 维度 | `src/automisc/tools/` (adapter) | `src/automisc/core/decoders/` (decoder) |
|---|---|---|
| **本质** | subprocess 调外部 CLI | 纯 Python 计算 |
| **每工具对应** | 一个 macOS 安装的 binary (e.g. `/usr/local/bin/7z`) | 一个纯函数 (e.g. `base64.b64decode()`) |
| **基类** | `ToolAdapter` (per `tools/base.py`) | 无基类, 直接注册 `DecoderSpec` |
| **注册装饰器** | `@register_tool` (per `core/registry.py`) | `register_decoder()` (per `core/decoders/registry.py`) |
| **返回类型** | `ToolResult` (含 stdout/stderr/duration/exit_code) | `DecodeResult` (含 output_text/output_bytes/error) |
| **GUI 渲染** | `menu_dock.TOOL_CATEGORIES` 静态映射 | `menu_dock._get_cipher_categories_from_registry()` 动态聚合 |
| **数量** | 18 adapter (file/strings/binwalk/.../sevenz_extract) | 28 decoder (12 cipher + 18 base/rot + 8 进制 + base64-image + coords-qr) |
| **典型例子** | sevenz → `/usr/local/bin/7z l` | caesar → `chr((ord(c) - shift) % 26)` |

### GUI 菜单分类 ↔ 后端位置速查

| GUI 菜单分类 | 后端位置 | 类型 |
|---|---|---|
| **共享基础工具** (file/strings/binwalk/...) | `tools/shared/` | adapter |
| **Stego/Image** (zsteg/stegseek) | `tools/steganography/image/` | adapter |
| **Forensics/Network** (tshark/tcpdump) | `tools/forensics/network/` | adapter |
| **Stego/Audio+Video** (ffmpeg/sox) | `tools/steganography/{audio,video}/` | adapter |
| **Misc/Archive** (sevenz/unzip/john/zip_classify) | `tools/misc/archive/` | adapter |
| **Forensics/Log** (grep/evtx_dump) | `tools/forensics/log/` | adapter |
| **Misc/Brainteaser** (zbar) | `tools/misc/brainteaser/` | adapter |
| **快捷工具** (fix_pseudo_zip/bruteforce_zip/...) | `core/actions/` | DAG Action |
| **🔓 Base64 → 图片** | `core/decoders/base64_image.py` | decoder |
| **🔢 进制转换** (8 个) | `core/decoders/base_convert.py` | decoder |
| **🔳 坐标 → 二维码** | `core/decoders/coords_to_qr.py` | decoder |
| **🔐 Base/ROT 解码** (18 个) | `core/decoders/base_rot_decoders.py` | decoder |
| **🔤 解密工具1** (12 cipher) | `core/decoders/cipher_decoders.py` | decoder |
| **📦 解密工具2/3** (占位 TBD) | `core/decoders/cipher_decoders.py` (placeholder) | decoder |
| **🔍 Magic Sniffer** (v0.5-lsb-byte-stream-extract) | `core/decoders/magic_sniffer.py` | decoder |
| **🐍 Pyc 反编译** (v0.5-pyc-magic-sniffer, **GUI 渲染 per v0.5-pyc-decompiler-gui + 3 按钮 per v0.5-pyc-decompiler-buttons**: 自动 / 强制 py2 / 强制 py3) | `core/decoders/pyc_decompiler.py` | decoder |

### 何时用 adapter vs decoder?

- **adapter** (tools/) — 需要调外部 binary (e.g. 解压 .vmdk 用 7z / 雕文件用 binwalk / 看图片用 exiftool)
- **decoder** (decoders/) — 纯计算就够 (e.g. base64 解码 / 凯撒 shift / BF 解释器)

**反例**: 把 cipher 写到 `tools/cipher/caesar.py` 写个 adapter 类, run() 只 return 计算结果 → 空壳, 违反分层. 正确位置是 `core/decoders/cipher_decoders.py:run_caesar`.

### 修改 GUI 工具栏显示

- **加 adapter** → `tools/<subpackage>/<name>.py` + `tools/<subpackage>/__init__.py` import + `tools/__init__.py` 双注册 + `menu_dock.TOOL_CATEGORIES` 加一行 + `ADAPTER_TOOLS` set 加 (per 双注册铁律)
- **加 decoder** → `core/decoders/<name>.py` 定义 `DecoderSpec` 并 `register_decoder()` → GUI 自动从 registry 渲染 (无需改 menu_dock)

---

## 3.6 extend-tools/ 跨平台 binary 分发（per v0.5-platform-extend-tools 治理变更）

> **背景**: macOS 上 Homebrew 装的 `binwalk` / `exiftool` / `7z` / `foremost` 全在 `/usr/local/bin`，subprocess 直接 `which` 命中。Windows 上没有 brew，4 个核心工具必须自带。
>
> **方案**: `extend-tools/` 目录 + 跨平台相对路径解析。

### 目录职责

| 子目录 / 文件 | 作用 | git |
|---|---|---|
| `bin/win-x64/` | Windows 二进制（binwalk.exe / exiftool.exe / 7zr.exe / foremost.exe） | ❌ **不入 git**（用 manifest 追溯） |
| `bin/macos/` | macOS 二进制（v0.5+ 暂留空，brew 优先） | — |
| `manifest.yaml` | 工具 URL + SHA256 + 版本（Owner 首次跑 install 时填 SHA256） | ✅ 入 git |
| `install.ps1` | Windows 自动下载脚本（幂等，已下跳过） | ✅ 入 git |
| `install.sh` | macOS 自动下载脚本（stub，brew 优先） | ✅ 入 git |
| `README.md` | 工具状态 + Windows 限制说明 | ✅ 入 git |

### 代码侧：`tools/paths.py`

```python
# 核心逻辑
def resolve_tool_binary(name: str) -> str | None:
    found = shutil.which(name)            # 1) PATH 优先
    if found:
        return found
    plat = {"win32": "win-x64", "darwin": "macos"}[sys.platform]
    candidate = EXTEND_TOOLS_BIN_DIR / plat / f"{name}{'.exe' if sys.platform == 'win32' else ''}"
    return str(candidate) if candidate.exists() else None   # 2) extend-tools fallback
```

### Adapter 改造模式

所有 adapter 把 `self.binary_path or "X"` 改成：
```python
from automisc.tools.paths import resolve_tool_binary
cmd = [self.binary_path or resolve_tool_binary("X") or "X"]
```

**效果**：macOS 走 PATH 不变，Windows 走 extend-tools/bin/win-x64/。

### 不可用工具

steghide / zsteg / stegseek 在 Windows 上不可用：
- GUI 菜单 marker = `✗`（v0.5-platform-extend-tools §3.4 增强）
- 点击执行 → ToolResult stderr `"executable not found: steghide"`
- zsteg **有自研替代** `lsb_detect` (per v0.5-lsb-detector)
- steghide **无替代**（v0.5+ 评估 Cygwin 编译）

### 完整设计

详见 [`upgrade/v0.5-platform-extend-tools.md`](upgrade/v0.5-platform-extend-tools.md)。

---

## 4. 工具池表 (per subflow)

| Subflow | 工具 |
|---|---|
| Forensics/Network | `tshark`, `tcpdump`, `pcap_protocol_router` (v0.5-pcap-protocol-router) |
| Forensics/Log | `grep`, `evtx_dump` |
| Forensics/Memory | `vol` (volatility3) |
| Stego/Image | `zsteg`, `steghide` |
| Stego/Audio | `sox`, `ffmpeg_audio`, `steghide_audio` |
| Stego/Video | `ffmpeg_video`, `ffprobe` |
| Misc/Archive | `sevenz_extract`, `unzip`, `john`, `zip_classify` (sevenz 探测类, GUI 不显示, per Owner 20:03) |
| Misc/Brainteaser | `zbar` (QR) |
| Shared | `binwalk`, `foremost`, `file`, `strings`, `xxd`, `exiftool` |

**auto-run 池** (拖入图片/zip/rar/其他文件, 自动跑, per AGENTS.md §1 铁律 7 = 纯探测不抢下一步):
- picture: `lsb_detect`, `stegseek`, `exiftool`, `binwalk`, `strings`, `file` (6 tools, **v0.5-lsb-detector 替代 zsteg**)
- traffic: `pcap_protocol_router`, `tshark`, `strings`, `file`
- archive: `sevenz`, `unzip` (列表 `-l`, 不实际解压), `zip_classify`, `file`, `strings`
- binary: `file`, `strings`, `binwalk`, `exiftool`

**v0.5-lsb-detector**: auto-run readonly 智能 LSB 检测 (替代 zsteg, 6 tools 不变) — RGB 3 通道 6 排列 × 2 scan = 12 组合, text 判定 (printable ASCII 32-126) + 文件头双机制 (hex magic 主 + `file` 命令辅) + 单通道 8 bit 概率检测 (entropy + unique count) — 字节流不写文件 (per 铁律 7 readonly), 命中写 journal SP sev=5 真可疑 / sev=4 info 概率

**v0.5-auto-run-suggest**: auto-run 命中后 (lsb_detect lsb_text / lsb_file_header / lsb_channel_anomaly + binwalk ZIP/7z/RAR/pyc / strings 敏感关键词) 写 suggest SP severity=4 "建议手工跑 X chain", **不**触发下一步 (per 铁律 7)

---

## 5. 链 (chain) 速查

| chain | DAG 拓扑 | 适用 |
|---|---|---|
| `zip` | try_unzip → fix_pseudo → 终止 | 已知是 zip (伪加密检测) |
| `zip-full` | try_unzip → fix_pseudo → bruteforce → 终止 | zip 真加密爆破 |
| `binwalk` | binwalk_extract (检测 + foremost 提取) | 复合文件分离 |
| `foremost` | foremost_extract (skip binwalk) | 已确认要 foremost |
| `lsb` | binwalk_extract → lsb_extract (zsteg-based) | PNG 隐写 + 自动路由(text 终止 / file 二次 router) |
| `lsb-bytes` | binwalk_extract → lsb_bytes_extract (PIL/numpy) | PNG/BMP/GIF 隐写 + 自定义通道位组合(per v0.5-lsb-byte-stream-extract, 跟 `lsb` 并行不冲突;**GUI Run→Chain 入口 + 4 参数 dialog per v0.5-lsb-bytes-gui**) |

CLI: `automisc chain --chain {name} --file <path> [--bruteforce-limit N]`
GUI: Run → Chain → Run {name} chain  
GUI: Run → Chain → Run lsb-bytes chain (4 params) → 弹 `LSBBytesParamDialog` (channels/bit/scan_order/byte_bit_order)

---

## 6. 文档入口（按使用频率）

| 文档 | 何时读 | 频率 |
|---|---|---|
| `AGENTS.md` | session 启动必读 (治理 + Git 流程) | 每次 |
| `STRUCTURE.md` | ← 本文件 (查模块作用) | 经常 |
| `upgrade.md` + `upgrade/<id>.md` | 每次新迭代必读 | 每次迭代 |
| `fix.md` + `upgrade/fix_<bug>.md` | 修 bug 前查 | 偶尔 |
| `prd.md` | 🟡 frozen (历史, 不读) | 不读 |
| `Architecture.md` | ❌ 已删 | 不读 |

---

## 7. 6 关验收速查（per AGENTS.md §1 铁律 4）

1. 代码已合并 main
2. `pytest -m "not integration"` 全绿（≤ 1min）
3. GUI 行为变更跑 `pytest -m integration` 跑通
4. 真实样本 smoke（≥ 1 个真实 misc 样本）→ 关键可疑点命中
5. Owner 自审（单 Owner 项目）
6. 文档同步（prd.md / upgrade.md / STRUCTURE.md 之一）

---

## 8. v0.5+ TODO（开放）

- 递归链（`recursive=True` 通用机制，foremost 抽出后自动接 zip chain）
- GUI 进度条 + cancel 按钮
- v0.5-1 disk adapters（yara / bulk_extractor / photorec — per `upgrade/v0.5-roadmap.md`）
- 真实题库回归测试集（≥ 5 题）

详 `upgrade.md` 索引。
