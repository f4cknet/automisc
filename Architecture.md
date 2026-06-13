# Architecture.md — AutoMisc 系统架构设计

> **角色**：automisc 的**架构设计**文档（4 层分层 + 模块依赖 + plug-in 机制 + 验证方法）
> **状态**：v0.1 启动（2026-06-13）
> **配套文档**：
> - [`AGENTS.md`](./AGENTS.md) — 项目治理（4 条铁律 + 违规分级 + AI Agent 条款）
> - [`prd.md`](./prd.md) — 需求 + 任务看板 + 演进路线图（单一事实来源）
> - [`tools.md`](./tools.md) — 外部 misc 工具清单 + adapter 适配说明（待 Owner 整理后建立）
>
> **本文档章节**：
> - §0 阅读指引
> - §1 分层模型（4 层单向依赖）
> - §2 GUI 层设计要点
> - §3 Core 调度层
> - §4 工具池层
> - §5 与 skill 体系的关系（明确**不桥接**）
> - §6 plug-in 机制
> - §7 验证方法
> - §8 演进路径（架构增量）
> - §9 兼容点预留

---

## 0. 阅读指引

| 你是谁 | 先看哪一节 |
|---|---|
| **第一次接触本项目** | **必读 [`AGENTS.md`](./AGENTS.md) §1 铁律** → 本文件 §1 → §3 → §6 |
| **理解为什么不桥接 skill** | §5 |
| **理解 4 层架构** | §1 + §3 + §4 |
| **正在写代码** | §1（分层边界）+ §3（Core API）+ §6（plug-in 规范）|
| **理解演进路径** | §8（v0.1 → v0.5 → v1.0 架构增量）|
| **AI Agent session 启动** | [`AGENTS.md §5`](./AGENTS.md) 4 步启动 → 本文件 §1 + §3 + §6 |

---

## 1. 分层模型（4 层 · 单向依赖）

### 1.1 分层图

```
┌─────────────────────────────────────────────────────────┐
│  GUI 层  (gui/)                                          │
│  - PySide6 QMainWindow                                   │
│  - 文件拖拽 / 菜单 / 输出区 / journal 面板                │
│  - 可疑点高亮渲染                                         │
├─────────────────────────────────────────────────────────┤
│  Core 调度层  (core/)                                    │
│  - 工具注册表（@register_tool 装饰器）                    │
│  - 入口分流器（file_path → subflow 推荐）                 │
│  - 可疑点扫描器（统一 schema 输出）                        │
│  - journal 自动记录                                       │
│  - 模板/DAG 编排（v0.5/v1.0 起）                         │
├─────────────────────────────────────────────────────────┤
│  工具池层  (tools/)                                      │
│  - ToolAdapter 抽象基类                                  │
│  - 5+ adapter 实现（binwalk / strings / foremost / ...）  │
│  - 统一返回 ToolResult（含可疑点列表）                    │
├─────────────────────────────────────────────────────────┤
│  外部工具  (macOS 系统 PATH)                              │
│  - binwalk / zsteg / foremost / tshark / vol.py / ...    │
└─────────────────────────────────────────────────────────┘

依赖方向严格自上而下，**禁止反向 import**。
```

### 1.2 分层职责

| 层 | 职责 | **不**做的事 |
|---|---|---|
| **GUI 层** | 用户交互（拖拽 / 菜单点击 / 输出展示）| ❌ 不做工具调用 / 不做可疑点扫描逻辑 / 不持久化数据 |
| **Core 调度层** | 工具调度 + 入口路由 + 可疑点聚合 + journal 记录 | ❌ 不做 UI 渲染 / 不直接调外部工具（调 adapter）/ 不持有 GUI 状态 |
| **工具池层** | 工具 adapter 实现（subprocess 包装 + 输出解析）| ❌ 不做调度决策 / 不做可疑点过滤（仅产出）/ 不直接写 journal |
| **外部工具** | 真正执行分析（macOS 系统 PATH 调用）| （无）|

### 1.3 依赖方向硬约束

| 允许 import | 禁止 import |
|---|---|
| GUI → Core | Core → GUI（反向耦合） |
| GUI → Tools | Core → 外部工具（必须经 Tools） |
| Core → Tools | Tools → Core（避免循环） |
| Tools → 外部工具（subprocess） | Tools → GUI |

**违反此约束的代码 = 违反铁律 1**，必须重构。

### 1.4 为什么这样分

- **Core 独立于 GUI**：未来加 CLI / Web 视图无需重写 Core（per `AGENTS.md §2.4` macOS only 约束下，GUI 仍可独立测试 Core）
- **adapter 独立于 Core**：新工具接入不动 Core（per §6 plug-in 机制）
- **外部工具经 Tools 层封装**：统一错误处理 / 超时控制 / 输出解析，避免 Core 直接 subprocess 满天飞

---

## 2. GUI 层设计要点

### 2.1 技术栈

- **框架**：PySide6（Qt 6.x 官方 Python 绑定）
- **平台**：macOS only（per `AGENTS.md §2.4`）
- **测试**：pytest-qt

### 2.2 主窗口结构

```python
# gui/main_window.py
from PySide6.QtWidgets import QMainWindow, QDockWidget

class MainWindow(QMainWindow):
    def __init__(self, core: CoreOrchestrator):
        super().__init__()
        self.core = core  # 注入 Core，不在 GUI 内 new Core

        # 文件拖拽
        self.setAcceptDrops(True)

        # 菜单树（左侧 QDockWidget）
        self.menu_dock = ToolMenuDock(self.core)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.menu_dock)

        # 输出区（中央 QPlainTextEdit）
        self.output_view = OutputView()  # 支持 ANSI 高亮
        self.setCentralWidget(self.output_view)

        # 底部标签页（输出 / journal / 可疑点 / 工具历史）
        self.bottom_tabs = BottomTabs()
        # ...
```

### 2.3 文件拖拽

```python
def dragEnterEvent(self, event):
    if event.mimeData().hasUrls():
        event.acceptProposedAction()

def dropEvent(self, event):
    file_paths = [url.toLocalFile() for url in event.mimeData().urls()]
    for fp in file_paths:
        recommendation = self.core.route(fp)  # 调用 Core
        self.show_recommendation_popup(fp, recommendation)
```

### 2.4 菜单树（六大分类）

```python
# gui/menu_dock.py
CATEGORIES = {
    "图片隐写": ["zsteg", "binwalk", "foremost", "exiftool", "steghide"],
    "流量分析": ["tshark", "tcpdump"],
    "压缩包": ["7z", "zip_pseudo_check", "bruteforce"],
    "内存取证": ["vol_imageinfo", "vol_cmdscan"],
    "编码解码": ["base64_decode", "rot13", "caesar", "vigenere", "jsfuck"],
    "二进制分析": ["strings", "binwalk", "file", "hexdump"],
}
```

### 2.5 输出区 + 可疑点高亮

- 使用 `QPlainTextEdit`（性能优于 `QTextEdit`）
- 自定义 `QSyntaxHighlighter` 子类，识别 ANSI 颜色码 + 可疑点关键字
- 可疑点列表同步到底部"可疑点列表"标签页

### 2.6 journal 面板

- 使用 `QTabWidget` 标签页之一
- 内容为 `solve_journal.md` 实时预览（per `prd.md §9.1` 布局）
- 菜单 → 文件 → 导出 journal → `QFileDialog.getSaveFileName`

### 2.7 GUI 与 Core 的边界

| GUI 可以 | GUI **不**可以 |
|---|---|
| 调用 `core.route(file_path)` | 直接调外部工具（subprocess / os.system）|
| 调用 `core.run_tool(tool_name, file_path)` | 自己解析工具输出 |
| 调用 `core.get_suspicious_points()` | 直接访问 adapter 内部 |
| 调用 `core.export_journal(path)` | 持久化任何数据（journal 由 Core 管）|

---

## 3. Core 调度层

> **关键抽象**：`CoreOrchestrator`（单一入口）+ `SuspiciousPoint`（统一可疑点 schema）+ `ToolResult`（工具返回）。

### 3.1 核心数据结构

```python
# core/suspicious.py
@dataclass
class SuspiciousPoint:
    id: str
    tool_name: str
    file_path: str
    category: str           # flag / webshell_family / file_header / base64_candidate / ...
    offset: int | None
    matched_pattern: str
    context: str
    severity: int           # 1-5
    suggested_action: str
    timestamp: datetime

# core/result.py
@dataclass
class ToolResult:
    tool_name: str
    exit_code: int
    stdout: str
    stderr: str
    suspicious_points: list[SuspiciousPoint]
    duration_ms: int
```

### 3.2 入口分流器（`core/router.py`）

```python
class FileRouter:
    def route(self, file_path: str) -> RouteRecommendation:
        # 1. python-magic 检测 MIME
        mime = magic.from_file(file_path, mime=True)

        # 2. 文件后缀
        suffix = Path(file_path).suffix.lower()

        # 3. 综合判定 → 推荐 subflow + 初始工具
        # （详见 prd.md §6 入口分流表）
        return RouteRecommendation(
            subflow=...,
            recommended_tools=[...],
            mime=mime,
            suffix=suffix,
        )
```

入口分流表见 [`prd.md §6`](./prd.md)。

### 3.3 工具注册表（`core/registry.py`）

```python
# core/registry.py
from functools import wraps

_TOOL_REGISTRY: dict[str, type[ToolAdapter]] = {}

def register_tool(cls: type[ToolAdapter]) -> type[ToolAdapter]:
    """工具 adapter 装饰器：注册到 _TOOL_REGISTRY"""
    _TOOL_REGISTRY[cls.name] = cls
    return cls

def get_tool(name: str) -> ToolAdapter:
    """根据名称实例化工具 adapter"""
    if name not in _TOOL_REGISTRY:
        raise ValueError(f"Tool not registered: {name}")
    return _TOOL_REGISTRY[name]()

def list_tools(category: str | None = None) -> list[str]:
    """列出所有工具（可选按分类过滤）"""
    if category is None:
        return list(_TOOL_REGISTRY.keys())
    return [name for name, cls in _TOOL_REGISTRY.items()
            if cls.category == category]
```

### 3.4 调度器（`core/orchestrator.py`）

```python
class CoreOrchestrator:
    def __init__(self):
        self.journal = Journal()
        self.router = FileRouter()

    def route(self, file_path: str) -> RouteRecommendation:
        return self.router.route(file_path)

    def run_tool(self, tool_name: str, file_path: str) -> ToolResult:
        # 1. 从 registry 取 adapter
        adapter = get_tool(tool_name)

        # 2. 调 adapter（adapter 内部 subprocess + parse）
        result = adapter.run(file_path)

        # 3. 写入 journal
        self.journal.append(tool_name, file_path, result)

        # 4. 返回 result（GUI 渲染用）
        return result

    def get_suspicious_points(self) -> list[SuspiciousPoint]:
        return self.journal.all_suspicious_points()

    def export_journal(self, path: str) -> None:
        self.journal.export(path)
```

### 3.5 可疑点扫描器（`core/suspicious.py`）

实现关键字 / 正则集合（per `prd.md §7`），所有 adapter 共用同一组规则：

```python
SUSPICIOUS_PATTERNS = {
    "flag": re.compile(r"(flag|ctf|key)\{[^}]*\}", re.IGNORECASE),
    "file_header": {
        "PK": b"PK\x03\x04",
        "RAR": b"Rar!\x1a\x07",
        "7z": b"7z\xbc\xaf\x27\x1c",
        "JPG": b"\xff\xd8\xff",
        "PNG": b"\x89PNG",
        "PDF": b"%PDF",
    },
    "webshell_family": {
        "behinder_v3": re.compile(r"eval\\(\\$_POST\\[\\w+\\]\\(\\)"),
        "caidao": re.compile(r"@eval\\(\\$\\$_POST\\["),
        "godzilla": re.compile(r"@\\$\\{.*\\}.*\\(\\)"),
    },
    "base64_candidate": re.compile(r"^[A-Za-z0-9+/]{16,}={0,2}$"),
    "base32_candidate": re.compile(r"^[A-Z2-7]{16,}={0,6}$"),
    "hex_string": re.compile(r"^[0-9A-Fa-f]{16,}$"),
    "keyword": ["password", "secret", "hidden", "encrypt", "cipher"],
}
```

### 3.6 journal（`core/journal.py`）

每次工具调用追加一段，格式沿用 misc-skill `solve_journal.md` 约定（per [`prd.md §1.3`](./prd.md)）：

```markdown
## 2026-06-13 10:30:25 — binwalk challenge.bin

**工具**：binwalk
**分类**：二进制分析
**文件**：`/path/to/challenge.bin`
**耗时**：1.2s

### 输出摘要
```
DECIMAL       HEXADECIMAL     DESCRIPTION
0             0x0             PNG image, 800 x 600
1024          0x400           Zip archive
```

### 可疑点（3 个）
- 🔴 [severity=5] `file_header: PK` @ offset 1024 — 检测到 ZIP 文件头，建议 foremost 分离
- 🟡 [severity=3] `base64_candidate` @ offset 2048 — 长度 64 的 base64 候选，建议尝试解码
- 🟢 [severity=1] `keyword: hidden` @ offset 3072 — 包含敏感关键字
```

### 3.7 Core 模块文件清单

```
core/
├── __init__.py
├── orchestrator.py        # CoreOrchestrator 入口
├── router.py              # FileRouter（入口分流）
├── registry.py            # @register_tool 装饰器
├── suspicious.py          # SuspiciousPoint + SUSPICIOUS_PATTERNS
├── result.py              # ToolResult dataclass
├── journal.py             # Journal 自动记录 + export
└── exceptions.py          # AutomiscError / ToolNotFound / ...
```

---

## 4. 工具池层

### 4.1 ToolAdapter 基类（`tools/base.py`）

```python
# tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ToolMeta:
    name: str               # "binwalk"
    category: str           # "binary_analysis"
    description: str        # 用户菜单显示
    binary_path: str | None # 外部工具路径（None = 走 PATH）

class ToolAdapter(ABC):
    name: str = ""
    category: str = ""
    description: str = ""
    binary_path: str | None = None

    @abstractmethod
    def run(self, file_path: str) -> ToolResult:
        """执行工具 + 解析输出 + 提取可疑点"""
        ...

    def check_available(self) -> bool:
        """检查外部工具是否在 PATH / 指定路径可用"""
        if self.binary_path:
            return Path(self.binary_path).exists()
        return shutil.which(self.name) is not None
```

### 4.2 adapter 实现（示例：binwalk）

```python
# tools/binwalk.py
import subprocess
from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter

@register_tool
class BinwalkAdapter(ToolAdapter):
    name = "binwalk"
    category = "binary_analysis"
    description = "扫描并提取文件中的嵌入文件"

    def run(self, file_path: str) -> ToolResult:
        # 1. subprocess 调 binwalk
        proc = subprocess.run(
            ["binwalk", file_path],
            capture_output=True, text=True, timeout=30
        )

        # 2. 解析输出（提取 DECIMAL / HEX / DESCRIPTION）
        # ...

        # 3. 提取可疑点（用统一 scanner）
        suspicious = scan_output_for_suspicious(
            tool_name=self.name,
            file_path=file_path,
            stdout=proc.stdout,
        )

        return ToolResult(
            tool_name=self.name,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            suspicious_points=suspicious,
            duration_ms=...,
        )
```

### 4.3 macOS subprocess 沙箱处理

**关键坑点**（per `AGENTS.md §2.4`）：

1. **PATH 不包含 Homebrew**：`/usr/local/bin`（Intel）或 `/opt/homebrew/bin`（Apple Silicon）
   - 解决方案：subprocess 时显式 `env={**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}`
2. **subprocess 输出污染**：pwntools 类工具的 stdout/stderr 区分
   - 解决方案：`subprocess.run(capture_output=True)` 分离 stdout/stderr
3. **macOS Gatekeeper**：未签名二进制首次运行需用户手动"打开"
   - 解决方案：README 写明首次运行步骤 + 在 tool check 时给清晰错误
4. **pyenv shims**：用户通过 pyenv 装的 Python 可能影响 subprocess 默认 Python
   - 解决方案：subprocess 时显式 `python3` 而不是 `python`

### 4.4 adapter 文件清单（per `prd.md §4.1 v0.1.0b` 2026-06-13 重整）

> **目录结构调整**：按 `tools.md §2` 的 11 个 subflow 重新组织。**Encoding 编码函数从 `tools/encoders/` 移到 `core/encoders/`**（per Owner 决策"编码分析自编写非工具池"）。

```
tools/                                   # 工具池层（外部工具 adapter）
├── __init__.py
├── base.py                              # ToolAdapter 基类
│
├── forensics/                           # Forensics 分支（per tools.md §3.1-3.4）
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── vol.py                       # P0 · ⚠️ v0.1 必须先恢复 vol2 安装
│   │   ├── strings_memory.py            # P0 · 共享 strings adapter
│   │   └── binwalk_memory.py            # P0 · 共享 binwalk adapter
│   ├── disk/
│   │   ├── __init__.py
│   │   ├── photorec.py                  # P1
│   │   ├── testdisk.py                  # P1
│   │   ├── sleuthkit.py                 # P1 · ❌ 需 brew install sleuthkit
│   │   └── sevenz_disk.py               # P1 · 共享 7z（VMDK/OVA 解压）
│   ├── network/
│   │   ├── __init__.py
│   │   ├── tshark.py                    # P0 · ✅ 已装
│   │   ├── tcpdump.py                   # P0 · ✅ 已装
│   │   ├── wireshark.py                 # P1 · GUI 辅助
│   │   ├── pcapfix.py                   # P1 · ❌ 需 brew install pcapfix
│   │   ├── aircrack.py                  # P1
│   │   └── multimon.py                  # P1 · DTMF/POCSAG
│   └── log/
│       ├── __init__.py
│       ├── grep.py                      # P0 · macOS 自带
│       ├── evtx_dump.py                 # P0 · ⚠️ 需 pip install python-evtx
│       └── sevenz_log.py                # P0 · 共享 7z（解 .evtx.bz2）
│
├── steganography/                       # Steganography 分支（per tools.md §3.5-3.7）
│   ├── __init__.py
│   ├── image/
│   │   ├── binwalk_image.py             # P0 · 共享
│   │   ├── zsteg.py                     # P0 · ✅ Ruby gem 已装
│   │   ├── steghide_image.py            # P0 · 共享
│   │   ├── exiftool_image.py            # P0 · 共享
│   │   ├── foremost_image.py            # P0 · 共享
│   │   ├── outguess.py                  # P1
│   │   ├── stegdetect.py                # P1
│   │   ├── stegseek.py                  # P1
│   │   ├── pngcheck.py                  # P1
│   │   ├── f5.py                        # P1 · ⚠️ 需 Java wrapper
│   │   └── stegolsb.py                  # P2
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── ffmpeg_audio.py              # P0 · ✅ 已装
│   │   ├── sox.py                       # P0 · ❌ 需 brew install sox
│   │   ├── steghide_audio.py            # P0 · 共享
│   │   └── mp3stego.py                  # P1 · ⚠️ 需 Wine
│   └── video/
│       ├── __init__.py
│       ├── ffmpeg_video.py              # P0 · 共享 ffmpeg
│       └── ffprobe.py                   # P0 · ✅ 已装
│
├── misc/                                # Misc Others 分支（per tools.md §3.9-3.11）
│   ├── __init__.py
│   ├── archive/
│   │   ├── sevenz.py                    # P0 · ✅ 已装（共享）
│   │   ├── unzip.py                     # P0 · ✅ 已装
│   │   ├── john.py                      # P0 · ❌ 需 brew install john-jumbo
│   │   ├── zipcrack.py                  # P0 · fallback（⚠️ 源码未软链）
│   │   └── hashcat.py                   # P1
│   ├── office/
│   │   ├── exiftool_office.py           # P0 · 共享
│   │   ├── binwalk_office.py            # P0 · 共享
│   │   ├── pdftotext.py                 # P1 · ⚠️ 需 brew install poppler
│   │   ├── mutool.py                    # P1 · ❌ 需 brew install mupdf-tools
│   │   └── python_docx.py               # P1
│   └── brainteaser/
│       ├── zbar.py                      # P0 · ❌ 需 brew install zbar
│       └── sqlite3.py                   # P1
│
└── shared/                              # 共享基础工具（per tools.md §3.12）
    ├── __init__.py
    ├── file.py                          # P0 · ✅ 已装
    ├── strings.py                       # P0 · ✅ 已装
    ├── binwalk.py                       # P0 · ✅ 已装（也可独立调用）
    ├── foremost.py                      # P0 · ✅ 已装
    ├── exiftool.py                      # P0 · ✅ 已装
    ├── xxd.py                           # P0 · ✅ 已装
    ├── hexdump.py                       # P1
    └── scalpel.py                       # P1

core/                                    # Core 调度层
└── encoders/                            # Encoding 内置实现（**非工具池层**）
    ├── __init__.py
    ├── base.py                          # P0 · base16/32/58/62/64/85/91/2048/32768/65536
    ├── classical.py                     # P0 · ROT13/47/18 + Caesar + Vigenère + Atbash + Pigpen + Keyboard Shift + Affine + Rail Fence
    ├── custom.py                        # P0 · BCD + IEEE 754 + UTF-16 endianness + Unicode Tags/Variation Selector + Multi-layer auto-decoder
    └── tests/
        └── ...                          # 单元测试
```

### 4.5 adapter 文件 vs tools.md 关系（v0.1 P0 重点关注）

| adapter 文件 | 对应 tools.md 工具 | 状态 | v0.1 PR |
|---|---|---|---|
| `tools/shared/binwalk.py` | [`tools.md §3.5 binwalk`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR1 |
| `tools/shared/strings.py` | [`tools.md §3.5 strings`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR1 |
| `tools/shared/foremost.py` | [`tools.md §3.5 foremost`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR1 |
| `tools/shared/exiftool.py` | [`tools.md §3.5 exiftool`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR1 |
| `tools/shared/file.py` | [`tools.md §3.5 file`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR1 |
| `tools/shared/xxd.py` | [`tools.md §3.12 xxd`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR1 |
| `tools/steganography/image/zsteg.py` | [`tools.md §3.5 zsteg`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR2 |
| `tools/steganography/image/steghide_image.py` | [`tools.md §3.5 steghide`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR2 |
| `tools/forensics/network/tshark.py` | [`tools.md §3.3 tshark`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR3 |
| `tools/forensics/network/tcpdump.py` | [`tools.md §3.3 tcpdump`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR3 |
| `tools/steganography/audio/ffmpeg_audio.py` | [`tools.md §3.6 ffmpeg`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR4 |
| `tools/steganography/video/ffprobe.py` | [`tools.md §3.7 ffprobe`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR4 |
| `tools/steganography/video/ffmpeg_video.py` | [`tools.md §3.7 ffmpeg`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR4 |
| `tools/misc/archive/sevenz.py` | [`tools.md §3.9 7z`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR5 |
| `tools/misc/archive/unzip.py` | [`tools.md §3.9 unzip`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR5 |
| `tools/misc/archive/john.py` | [`tools.md §3.9 john`](./tools.md) | ❌ v0.1 必须装 `brew install john-jumbo` | v0.1.0b-PR5 |
| `tools/forensics/log/grep.py` | [`tools.md §3.12 grep`](./tools.md) | ✅ 已装可写 | v0.1.0b-PR6 |
| `tools/forensics/log/evtx_dump.py` | [`tools.md §3.4 evtx_dump`](./tools.md) | ⚠️ 需 `pip install python-evtx` | v0.1.0b-PR6 |
| `tools/forensics/memory/vol.py` | [`tools.md §3.1 vol.py`](./tools.md) | ⚠️ **必须先恢复 vol2 安装**（blocker） | v0.1.0b-PR7 |
| `tools/misc/brainteaser/zbar.py` | [`tools.md §3.8 zbarimg`](./tools.md) | ❌ v0.1 必须装 `brew install zbar` | v0.1.0b-PR8 |
| `tools/steganography/audio/sox.py` | [`tools.md §3.6 sox`](./tools.md) | ❌ v0.1 必须装 `brew install sox` | v0.1.0b-PR4 追加 |
| `tools/shared/python_magic_bin.py` | [`tools.md §4 python-magic-bin`](./tools.md) | ❌ v0.1 必须 `pip install python-magic-bin` | v0.1.0b-PR9 |
| `tools/shared/numpy.py` | [`tools.md §4 numpy`](./tools.md) | ❌ v0.1 必须 `pip install numpy` | v0.1.0b-PR9 |

**v0.1 P0 adapter 总数**：**22 个**，分 9 个 PR 实施（per [`tools.md §6.2`](./tools.md) + [`AGENTS.md §2.1`](./AGENTS.md) ≤400 行/PR 约束）。

**Encoding 编码函数（`core/encoders/`）**：**不计入 adapter 数**，3 个 Python 模块（base / classical / custom）共 9h 实现。
| `tools/john.py` | [`tools.md §3.3 john`](./tools.md) | ❌ v0.1 需 `brew install john-jumbo` |
| `tools/zbar.py` | [`tools.md §3.8 zbarimg`](./tools.md) | ❌ v0.1 需 `brew install zbar` |
| `tools/sox.py` | [`tools.md §3.6 sox`](./tools.md) | ❌ v0.1 需 `brew install sox` |

> **adapter 实施顺序**：先 ✅ 工具吃满（≥8 个），再回头补 ❌ 工具的安装 + adapter。

---

## 5. 与 skill 体系的关系（明确**不桥接**）

### 5.1 明确边界

> **`misc/skills/*SKILL.md` 是给 AI Agent 用的，automisc 不消费它们。**

| 维度 | `misc/skills/*SKILL.md` | `misc/automisc` |
|---|---|---|
| 目标用户 | AI Agent（LLM 阅读后执行）| 人（CTF 选手手动操作）|
| 形态 | Markdown 文档（流程描述）| macOS GUI 应用 |
| 执行者 | LLM 按 skill 指引调用工具 | Core 调度 + GUI 触发 |
| 工具调用 | LLM 自行决定 | Core + adapter |
| 网络依赖 | 无（但 LLM 本身在线）| 完全离线 |

### 5.2 为什么不桥接

- **场景不同**：skill 是 AI Agent 解题流程指引，automisc 是选手手动工具
- **桥接成本高**：要把 skill 的 markdown 流程转成 Core 可执行的模板需要 parser + executor，工程量大且收益小
- **可能引入 LLM 依赖**：桥接 skill 最自然的实现是让 LLM 解析 skill 内容，违反完全离线约束

### 5.3 引用方式

如果某些 skill 中的具体脚本实现很好用，**可以单独 import**（不桥接 skill 本身）：

```python
# tools/zip_pseudo_check.py — 复用 misc-skill 的脚本实现
import sys
sys.path.append("../../misc/skills/misc-skill/scripts")
from zip_pseudo_encryption_check import check_pseudo_encryption
```

但这仅限**脚本级 import**，**不桥接 skill 文档本身**。

---

## 6. plug-in 机制

### 6.1 设计目标

> **新增工具 = 写一个 adapter + `@register_tool`，不动 Core。**

### 6.2 adapter 接入流程

1. 在 `tools/` 下创建 `<tool_name>.py`
2. 继承 `ToolAdapter`
3. 实现 `run(file_path) -> ToolResult`
4. 用 `@register_tool` 装饰类
5. 在 `tools/__init__.py` import 这个文件（确保装饰器执行）

```python
# tools/strings.py
from automisc.core.registry import register_tool
from automisc.tools.base import ToolAdapter

@register_tool
class StringsAdapter(ToolAdapter):
    name = "strings"
    category = "binary_analysis"
    description = "提取文件中的可打印字符串"

    def run(self, file_path: str) -> ToolResult:
        # 实现...
        ...
```

### 6.3 adapter 自动发现

`tools/__init__.py` 显式 import 所有 adapter：

```python
# tools/__init__.py
from .binwalk import BinwalkAdapter
from .strings import StringsAdapter
from .foremost import ForemostAdapter
from .tshark import TsharkAdapter
from .exiftool import ExiftoolAdapter
# ... 新 adapter 加一行
```

**未来可选优化**：用 `importlib` 自动扫描（v0.5+ 候选）。

### 6.4 GUI 自动发现菜单

`gui/menu_dock.py` 启动时调用 `core.list_tools()`，自动构建菜单树：

```python
# gui/menu_dock.py
def build_menu(self, core: CoreOrchestrator):
    for category in ["图片隐写", "流量分析", ...]:
        tools = core.list_tools(category=category)
        for tool_name in tools:
            action = QAction(tool_name, self)
            action.triggered.connect(lambda: self.core.run_tool(tool_name, ...))
            self.category_menu[category].addAction(action)
```

新工具接入后，**无需改 GUI 代码**，重启即可出现在菜单。

---

## 7. 验证方法

> **6 关验收（必跑）**：每条都 ✅ 才能把状态从 🔄/👀 改 ✅。

### 7.1 关 1: 代码已合并到 main

- PR target = main
- 合并后 working tree clean
- `git log main --oneline -1` 显示当前 commit

### 7.2 关 2: pytest unit 全过

```bash
pytest tests/unit/ -m "not integration" -q
```

**当前基准**：v0.1 启动时 0 tests（首个 commit 加）

### 7.3 关 3: pytest GUI 集成（若涉及 GUI 行为变化）

```bash
pytest tests/integration/ -q
```

使用 `pytest-qt`：
- 文件拖拽测试（`QDragEnterEvent` 模拟）
- 菜单点击测试（`QTest.mouseClick`）
- 输出区渲染测试（断言高亮关键字出现）

**CI 注意事项**：GitHub Actions `macos-latest` runner 可用但慢 + 资源少，v0.1 集成测试先在本地手动跑，v0.3 再上 CI。

### 7.4 关 4: 真实样本 smoke（若涉及 Core 工具调用行为）

准备 3 个真实 misc 样本（图片 / 流量 / 压缩各 1）：
- 拖入样本 → 跑核心 adapter → 对比 journal 关键可疑点命中一致
- log 输出到 `logs/v<X>.<Y>-smoke/`

**当前基准**：v0.1 启动时无样本（首个 commit 加 fixture）

### 7.5 关 5: Owner 自审

- 单 Owner 项目（per [`AGENTS.md §2.2`](./AGENTS.md)）
- PR 描述含：任务 ID / 实施要点 / Refs:[`prd.md §3`](./prd.md) 任务行

### 7.6 关 6: 文档同步

- **同一 PR** 更新 [`prd.md §3`](./prd.md) 任务行（状态 + 实际工时 + commit SHA）
- **同一 PR** 更新本文件（如涉及架构变更）

### 7.7 工具脚本（v0.1+ 候选）

| 工具 | 用途 | 何时用 |
|---|---|---|
| `pytest tests/unit/ -m "not integration"` | Core 单测 | 每次改 Core 后必跑（关 2）|
| `pytest tests/integration/` | GUI 集成 | 改 GUI 时必跑（关 3）|
| `python -m automisc` | 启动 GUI | 本地开发 / 真实样本 smoke（关 4）|

---

## 8. 演进路径（架构增量）

### 8.1 v0.1 → v0.5（模板编排）

**新增层 / 模块**：

```
core/
├── orchestrator.py        # 不变
├── template.py            # 🆕 Template 抽象类 + 顺序执行
└── templates/             # 🆕 预设模板
    ├── pcap_webshell.py   # pcap_webshell_check
    ├── image_stego.py     # image_stego_check
    └── archive_crack.py   # archive_crack
```

**改动范围**：
- ✅ 新增 `core/template.py` + `core/templates/`
- ✅ GUI 新增"自动分析"按钮（菜单 → 模板选择 → 执行）
- ❌ 不动 `tools/`（adapter 不变）
- ❌ 不动 GUI 主体（菜单树 / 输出区 / journal 不变）

### 8.2 v0.5 → v1.0（DAG 编排）

**新增层 / 模块**：

```
core/
├── orchestrator.py        # 不变
├── dag.py                 # 🆕 DAG 引擎（基于数据依赖）
└── type_system.py         # 🆕 工具输出 type 声明

tools/
└── 每个 adapter 新增 outputs 字段声明产出类型
```

**改动范围**：
- ✅ 新增 `core/dag.py` + `core/type_system.py`
- ✅ 所有 adapter 加 `outputs: list[str]` 字段（如 `["extracted_files", "text_strings"]`）
- ✅ GUI 新增"编排视图"标签页（可视化 DAG 节点状态）
- ❌ 不动 `tools/base.py`（基类接口不变，仅加可选字段）

### 8.3 明确不演进的方向

| ❌ 不做 | 原因 |
|---|---|
| **不引入 LLM 编排决策** | 完全离线产品（per [`prd.md §3.2`](./prd.md) 非范围硬约束）|
| **不桥接 `misc/skills/*SKILL.md`** | skill 是给 AI Agent 用的，automisc 不消费（per §5）|
| **不做跨平台** | macOS only |
| **不做云端同步 / Web UI** | 完全离线桌面工具 |

---

## 9. 兼容点预留（v0.1 就要考虑）

> **以下设计原则在 v0.1 就要落地，为 v0.5 / v1.0 演进铺路**。

### 9.1 adapter 输出统一 schema

每个 adapter 必须返回 `ToolResult`（含 `suspicious_points: list[SuspiciousPoint]`），**不允许返回裸字符串或 dict**。

**为什么**：v1.0 DAG 引擎需要 type system 推断数据流；统一 schema 是前置条件。

### 9.2 工具按"产出类型"分类（v0.1 软约束）

虽然 v0.1 不实现 type system，但 adapter docstring 建议标注产出类型：

```python
class BinwalkAdapter(ToolAdapter):
    """
    产出类型：
      - extracted_files: list[Path]  # foremost 分离的文件
      - file_headers: list[tuple[bytes, int]]  # (magic, offset)
    """
```

v1.0 起把 docstring 升级为 `outputs: list[str]` 类字段。

### 9.3 Core 调度层不假设"单次调用"

`core.run_tool(tool_name, file_path)` 接受单文件，**但内部不假设 GUI 一次只调一次**。

**为什么**：v0.5 模板编排 = Core 多次串行调用 `run_tool`；v1.0 DAG = Core 并发 / 条件调用。接口稳定 = 调用方式可演进。

### 9.4 工具调用结果**累积**而非丢弃

`core.journal.all_suspicious_points()` 返回**所有历史**可疑点，**不仅当前次**。

**为什么**：GUI 可疑点列表标签页 = 全局视图；journal 导出 = 完整记录。

### 9.5 macOS only 假设写进代码

不做 `sys.platform == "darwin"` 分支（per [`AGENTS.md §2.4`](./AGENTS.md)），假设永远是 macOS。

**为什么**：跨平台 hack 会让 Core 测试矩阵翻 3 倍，对单 Owner 项目不值得。

---

## 10. 变更日志

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-13 | 1.0 | 初版：4 层分层模型 + GUI 设计要点 + Core 调度层 API + 工具池 adapter 模式 + 与 skill 体系不桥接 + plug-in 机制 + 6 关验证方法 + 演进路径（v0.1→v0.5→v1.0）+ 兼容点预留。骨架参考 `pwn/autopwn/refactor.md §3 目标架构`，按 automisc 特性调整：4 层（GUI/Core/Tools/External）替代 7 层；明确 macOS only 单一假设；明确不桥接 skill；明确不引入 LLM |
| 2026-06-13 | **1.1** | **v0.1.0b-PR1 实施落地**（per [`prd.md §4.1`](./prd.md)）：实现 `core/{result,suspicious,registry,orchestrator}.py` + `tools/base.py` + `tools/shared/{file,strings,binwalk,foremost,exiftool,xxd}.py`；**61 个 pytest unit 测试全过**；真实样本 smoke 命中关键可疑点（flag/PNG magic/base64/file_header）。**PR1 同步更新**：`§4.4` adapter 文件清单中的 PR1 6 个 ✅ adapter 从"待写"变"已实现"。**未做的事**（per `tools.md §6.2`）：PR2-PR9（Stego/Network/Audio+Video/Archive/Log/Memory/Brainteaser/Python 包）尚未实施 |

---

> **最后一条**：
> 本文档是 automisc 的**架构设计**单一事实来源。任何"代码结构 / 模块边界 / 依赖方向"问题先查这里。
> 需求演进在 [`prd.md`](./prd.md) + 治理在 [`AGENTS.md`](./AGENTS.md)。