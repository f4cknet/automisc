# fix_decoder_registry_pyc_magic (2026-07-01 00:35)

| 字段 | 值 |
|---|---|
| **类型** | 🟢 fix（GUI registry 漏注册，Owner 实战 flag.pyc 触发） |
| **触发** | Owner 2026-07-01 00:24 跑 GUI 拖入 `flag.pyc` (Python 2.7, 755B, magic `03 f3 0d 0a`) → auto-run 跑完 4 个工具（3/4 OK）→ Owner 手工点左侧 "🐍 Pyc 反编译" → DecodeRunner 报 `ValueError: unknown decoder: pyc_decompiler` |
| **根因** | v0.5-lsb-byte-stream-extract (main `17f0784` 之前) + v0.5-pyc-magic-sniffer (main `17f0784`) 加新 decoder (`magic_sniffer` + `pyc_decompiler`) 时，**只**在 `src/automisc/__main__.py:319-322` 显式 import 触发 CLI 路径，**漏**了 `src/automisc/core/decoders/__init__.py:26-30` 这边的 side-effect import。GUI 启动路径走 `main_window.py:21` 的 `from automisc.core import decoders as _decoders` → 触发 `__init__.py` 的 side-effect → 这 2 个 decoder 不在列表里 → registry 没注册 → `get_decoder("pyc_decompiler")` 返回 `None` → DecodeRunner 抛 `unknown decoder`。**同类 bug 已记**: `main_window.py:14` 注释明确说"GUI 菜单栏 [coords-qr] 触发时 DecodeRunner 报 'unknown decoder: coords-qr'" — 当时只修 coords-qr 单点，没意识到是架构层统一漏 |
| **实战位置** | `C:\Users\zmzsg\Downloads\flag\flag.pyc` → GUI 工具栏点 "🐍 Pyc 反编译" → 失败 |
| **影响范围** | GUI 触发 `decoder:pyc_decompiler` + `decoder:magic_sniffer` 都报 "unknown decoder"。CLI 路径 `automisc decode pyc_decompiler --file X` **不**受影响（per `__main__.py:316-322` 显式 import 触发） |

## 1. Fix 决策（per AGENTS §1 铁律 2 → 实战 1 道同类不升架构，per §5.2；本 fix 是修 GUI bug 不是新增架构能力）

### 1.1 修法选型

| 候选 | 描述 | 取舍 |
|---|---|---|
| **A. 显式 side-effect import** | 在 `core/decoders/__init__.py` 加 2 行 `from automisc.core.decoders import magic_sniffer / pyc_decompiler` (跟现有 5 行同模板) | ✅ 选 — 跟 v0.5-coords-qr-fix (`main_window.py:14` 注释里的同类 bug) 修法一致；0 新基础设施；2 行 5min 改完 |
| **B. `__init__.py` 自动扫 `*.py`** | `__init__.py` 写 `import pkgutil; for m in pkgutil.iter_modules(__path__): importlib.import_module(...)` | ❌ 不选 — 改动大，触发顺序不可控（依赖关系复杂的 decoder 可能 race）；实战 1 道同类不升架构（per §5.2）；且 owner 后续期望 v0.5+ 新 decoder 走更显式 checklist（见 §5 沉淀） |
| **C. CI 检查新 decoder 必须双 import** | 加 lint/test 校验 `core/decoders/*.py` 新文件必须在 `__init__.py` + `__main__.py` 都 import | ⚠️ 边界 — 实战 1 道同类**不**足以证明必须 CI lint；先 fix 当前 bug + 加单测断言（per A 方案 §2.3），将来实战 ≥ 3 道同类再考虑升 lint |
| **D. 仅改 doc 提示用户走 CLI** | 文档说"pyc_decompiler 只支持 CLI，GUI 暂不可用" | ❌ 拒 — 直接劣化 GUI 工具栏（v0.5-pyc-decompiler-gui 才加的入口），跟 Owner 决策 "automisc 主走 GUI" 方向相反 |

### 1.2 取舍佐证

**选 A 理由**：
1. 跟 `main_window.py:14` 注释里 coords-qr 同类 bug 的**修法风格一致**（当时 v0.5-coords-qr-fix 是显式 `from automisc.core import decoders as _decoders`，但**只**修了那个点；本 fix 把整个 v0.5+ 加的新 decoder 一并补齐 side-effect import）
2. A 方案**0 新基础设施**：复用现有 `register_decoder()` 装饰器模式
3. A 方案单测可控：测试断言 `get_decoder("pyc_decompiler") is not None` + `from automisc.core import decoders` 后**re-import 也必须注册**
4. A 不影响 `__main__.py`：`__main__.py:319-322` 显式 import 是为了 CLI 触发 `_decode_subparser.add_parser(spec.name, ...)`，跟 `__init__.py` side-effect 是**不同目的**，两边 import 都要保留
5. 修法跟 fix_qemu_img_friendly_error 决策风格一致（owner 实战触发 + 局部修 + 不升架构）

**为什么不动 B 方案（自动扫）**：
- B 改 `__init__.py` 整文件 → 触发顺序 race 风险（cipher_decoders 里 placeholder 注册顺序、base_rot_decoders 里 18 个注册顺序都可能被打乱）
- 实战 1 道同类**不**足以证明"自动扫"比"显式 import"更稳
- A 方案已经够 owner 实战用（GUI 触发就跑），将来真要自动化再单独 spec

**为什么不动 C 方案（CI lint）**：
- C 是普适改动（影响所有 v0.5+ decoder 的添加流程）
- 实战 1 道同类**不**足以证明"所有 v0.5+ decoder 都该走 lint"
- A + 单测断言已覆盖（per §2.3），将来实战 ≥ 3 道同类再加 lint

## 2. 实施

### 2.1 `core/decoders/__init__.py` 改 `__all__` + 加 side-effect import

**diff**：
```python
 # 触发所有 decoder 注册 (import side-effect)
 from automisc.core.decoders import base64_image  # noqa: F401, E402
 from automisc.core.decoders import base_convert  # noqa: F401, E402
 from automisc.core.decoders import coords_to_qr  # noqa: F401, E402
 from automisc.core.decoders import base_rot_decoders  # noqa: F401, E402  # v0.5-base-rot-decoders
 from automisc.core.decoders import cipher_decoders  # noqa: F401, E402  # v0.5-cipher-decoders (12 cipher + 2 placeholder)
+# fix_decoder_registry_pyc_magic (per Owner 2026-07-01 实战 flag.pyc):
+# v0.5-lsb-byte-stream-extract (magic_sniffer) + v0.5-pyc-magic-sniffer (pyc_decompiler)
+# 之前只在 __main__.py 显式 import 触发 CLI 路径, 漏了 __init__.py 这边
+# → GUI 路径走 `from automisc.core import decoders` 触发不到, DecodeRunner 报
+# "unknown decoder: pyc_decompiler" (同 main_window.py:14 注释里 coords-qr 同类 bug).
+# 修法: 在这里也 side-effect import, 让 GUI 启动时 registry 必含这 2 个.
+from automisc.core.decoders import magic_sniffer  # noqa: F401, E402  # v0.5-lsb-byte-stream-extract
+from automisc.core.decoders import pyc_decompiler  # noqa: F401, E402  # v0.5-pyc-magic-sniffer
```

**`__all__` 同步加 2 个**：
```python
     "cipher_decoders",
+    "magic_sniffer",  # v0.5-lsb-byte-stream-extract
+    "pyc_decompiler",  # v0.5-pyc-magic-sniffer
 ]
```

### 2.2 `__main__.py` 不动

`__main__.py:319-322` 已经显式 import 了 `magic_sniffer` + `pyc_decompiler`（CLI 触发 `_decode_subparser.add_parser(spec.name)` 需要 registry 已就位）。两边 import 是**不同目的**：

| 文件 | 目的 | 影响 |
|---|---|---|
| `core/decoders/__init__.py` | GUI 路径 `from automisc.core import decoders` 触发 side-effect | GUI 工具栏 / DecodeRunner |
| `__main__.py` | CLI 路径 `automisc decode <name> --file X` 触发 argparse subparser 动态生成 | CLI subparser |

两边 import 都保留（per `__main__.py:316-322` 注释 "触发 decoder 注册 (import 一次即生效)"）。

### 2.3 单测（`tests/unit/gui/test_text_only_decoders.py` 加 3 个回归 case）

**改动 1**：更新 `EXPECTED_FILE_BASED_DECODERS` 列表：
```python
EXPECTED_FILE_BASED_DECODERS = [
    "base64-image",  # 解 base64 编码的图片, 走 file
    "coords-qr",     # 解 QR PNG 文件, 走 file (override)
    # v0.5-lsb-byte-stream-extract: 字节流 magic 嗅探, 走 file (per core/decoders/magic_sniffer.py:184)
    "magic_sniffer",
    # v0.5-pyc-magic-sniffer: pyc 反编译, 走 file (per core/decoders/pyc_decompiler.py:184)
    "pyc_decompiler",
]
```
（之前 v0.5-lsb-byte-stream-extract / v0.5-pyc-magic-sniffer 实施时漏更新这列表，所以 `test_no_decoder_has_unexpected_text_only` 也漏命中 — 本 fix 一并补）

**改动 2**：加 2 个新回归 case（防止 v0.5+ 后续加 decoder 时再漏）：
```python
EXPECTED_DECODERS_AFTER_REGISTRY_FIX = {
    "magic_sniffer",   # v0.5-lsb-byte-stream-extract
    "pyc_decompiler",  # v0.5-pyc-magic-sniffer
}


def test_registry_contains_magic_sniffer_and_pyc_decompiler():
    """registry 必须含 magic_sniffer + pyc_decompiler (fix_decoder_registry_pyc_magic)."""
    for name in EXPECTED_DECODERS_AFTER_REGISTRY_FIX:
        spec = get_decoder(name)
        assert spec is not None, (
            f"{name} 未注册到 registry (registry import 漏? 见 fix_decoder_registry_pyc_magic)"
        )


def test_decoder_init_side_effect_imports_v0_5_decoders():
    """`from automisc.core import decoders` 必须触发所有 v0.5+ decoder side-effect 注册."""
    import importlib
    import automisc.core.decoders as dec_pkg
    importlib.reload(dec_pkg)  # 模拟 GUI 重启
    for name in EXPECTED_DECODERS_AFTER_REGISTRY_FIX:
        spec = get_decoder(name)
        assert spec is not None, (
            f"reload(decoders) 后 {name} 仍未注册, "
            f"side-effect import 在 __init__.py 漏了 (regression)"
        )
```

### 2.4 其他文件不动

- `core/decoders/pyc_decompiler.py` — 已经是 `text_only=False`（per `:184`），符合 file-based 语义
- `core/decoders/magic_sniffer.py` — 已经是 `text_only=False`（per `:233`），符合 file-based 语义
- `gui/main_window.py:21` — 已经 `from automisc.core import decoders as _decoders` 触发 side-effect，A 方案修完即可生效
- `gui/decode_runner.py:72-76` — `get_decoder(name)` 返回 `None` → 抛 `unknown decoder`，逻辑正确（修复后 registry 必含，错误路径走不到了）
- `__main__.py:316-322` — 已经显式 import，CLI 路径不受影响
- `STRUCTURE.md` — 不动（`core/decoders/pyc_decompiler.py` + `core/decoders/magic_sniffer.py` 已经在 §3 模块表里）
- `tests/unit/core/decoders/test_pyc_decompiler.py:168-181` — 已经覆盖 "pyc_decompiler 必须注册到 registry"，本 fix 在这之上**再加 2 个跨 decoder 的断言**

## 3. 验证

### 3.1 单测验证

- `tests/unit/gui/test_text_only_decoders.py` 全套（包含新加 2 个 case）：**30+ passed**
- `tests/unit/core/decoders/test_pyc_decompiler.py` 全套：8 passed, 2 skipped (owner-specific smoke)
- `tests/unit/core/decoders/test_magic_sniffer.py` 全套：25+ passed
- `tests/integration/gui/test_pyc_decompiler_gui.py` 全套：4 passed, 1 skipped (opt-in smoke)
- 回归：无新增失败（`test_coords_to_qr.py::test_no_file_path_falls_back_to_tmp` 失败是 Windows 路径 pre-existing，跟本 fix 无关）

### 3.2 实战验证（per Owner 2026-07-01 跑通）

```
> python -c "from automisc.core import decoders as _d; from automisc.core.decoders.registry import get_decoder, list_decoders; print('total:', len(list_decoders())); print('pyc_decompiler:', get_decoder('pyc_decompiler') is not None); print('magic_sniffer:', get_decoder('magic_sniffer') is not None)"
total: 44
pyc_decompiler: True
magic_sniffer: True
```
（修复前：`total: 42, pyc_decompiler: False, magic_sniffer: False` — `__init__.py` 漏了 2 个 side-effect import）

### 3.3 GUI 端到端（per Owner 2026-07-01 重启 GUI 后）

GUI 工具栏点 "🐍 Pyc 反编译" → DecodeRunner 不再报 "unknown decoder" → 调 `run_pyc_decompiler(file_path)` → 走 xdis 路径（依赖装好后能反编译 Py2.x flag.pyc）

## 4. 影响

- 0 新依赖（不引入 xdis / uncompyle6 / decompyle3 — 那是 v0.5-pyc-deps-install 范围）
- 0 GUI 行为变更（只是 GUI 路径触发的 registry 终于完整）
- 0 base.py / adapter 改动（纯 core/decoders 范围）
- 0 新基础设施（复用现有 `register_decoder()` + `get_decoder()` 机制）
- 实战触发 1 道同类（flag.pyc pyc_decompiler 失败）— 实战 ≥ 3 道同类再考虑升架构（auto-import 或 CI lint）

## 5. 沉淀（per §5.4 失败题归档规范）

**根因类别**：v0.5+ 加新 decoder 时**忘了**同时 import 到 `core/decoders/__init__.py` + `tests/unit/gui/test_text_only_decoders.py::EXPECTED_FILE_BASED_DECODERS`

**v0.5+ 加新 decoder checklist**（建议加进 `AGENTS.md §7 文档引用速查` 或新建 `docs/decoders.md`，等实战 ≥ 3 道同类升架构时再实施）：
1. 新建 `core/decoders/<name>.py` + `register_decoder(DecoderSpec(...))`
2. **必须**在 `core/decoders/__init__.py` 加 side-effect import（GUI 路径）
3. **必须**在 `__main__.py` 加 side-effect import（CLI 路径，已在 v0.5 模板里）
4. **必须**更新 `tests/unit/gui/test_text_only_decoders.py::EXPECTED_FILE_BASED_DECODERS`（如果 text_only=False）或 `EXPECTED_TEXT_ONLY_DECODERS`（如果 text_only=True）
5. 加单测覆盖 `get_decoder(name) is not None`
6. CI 跑 `pytest tests/unit/core/decoders tests/unit/gui/test_text_only_decoders -q` 验证

**目前 checklist 仅在本文档 §5 沉淀**，**不**并入 AGENTS（实战 1 道同类，per §5.2 不升架构）。

## 6. 关联

- **实战样本**：`C:\Users\zmzsg\Downloads\flag\flag.pyc`（755B, Python 2.7, magic `03 f3 0d 0a`）
- **同类 bug 历史**：`src/automisc/gui/main_window.py:14` 注释里 v0.5-coords-qr-fix（当时只修了 coords-qr 单点）
- **被修复的 spec**：
  - [`v0.5-lsb-byte-stream-extract.md`](./v0.5-lsb-byte-stream-extract.md) — 加 `magic_sniffer` decoder，漏 `__init__.py` import
  - [`v0.5-pyc-magic-sniffer.md`](./v0.5-pyc-magic-sniffer.md) — 加 `pyc_decompiler` decoder，漏 `__init__.py` import
- **关联 fix**：本次 fix 后，B 步骤 `v0.5-pyc-deps-install`（`install.ps1` 加 xdis / uncompyle6 / decompyle3）才能让 GUI 反编译跑通
- **AGENTS §7 速查**：修复记录 `fix_<bug>.md` 在 `upgrade/` 子目录（per 2026-06-28 治理澄清）