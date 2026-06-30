# fix.md — 修复记录索引

> **维护策略**（per `AGENTS.md §6.1`）：只列已 merge 的 fix。  
> 单 fix 详细记录 → `upgrade/fix_<bug_name>.md`（永久保留，git blame / audit 用）。  
> **路径修正 (2026-06-28 per Owner)**: `fix_<bug_name>.md` 应在 `upgrade/` 子目录（跟 `upgrade/v0.5-*.md` 迭代 spec 同级），不在项目根。  
> 未做 / TODO → 走 `prd.md §3` 任务看板，**不进** `fix.md`。

| fix ID | bug_name | 关联任务行 | 一句话描述 | 状态 |
|---|---|---|---|---|
| v0.5-gui-zip-full | `gui_zip_trigger_no_bruteforce` | v0.5-LSB-router-GUI | GUI `_maybe_trigger_zip_chain_from_binwalk` 走 `build_zip_chain_dag`（无 bruteforce）→ 真加密 zip 永远 fail | ✅ done (commit (待 push)) |
| v0.5-base64-image-file-windows | `base64_image_file_windows` | v0.5-base64-image | `core/decoders/base64_image.py:_file_detect` 用 `shutil.which("file")` Win 端 None → 抛 "file 检测: (empty / no file command)"；改用 `resolve_tool_binary("file")` 走 extend-tools/bin/win-x64/file.exe fallback | ✅ done (commit (待 push)) |
| v0.5-resolve-tool-binary-subdir | `resolve_tool_binary_subdir` | v0.5-stegseek-remove | `automisc/tools/paths.py:resolve_tool_binary` 只看 flat 布局 `bin/<name>.exe`，不查 subdir 布局 `bin/<name>/<name>.exe` → steghide Cygwin build (DLL 依赖必须同目录) Win 端永远找不到。修后 +8 单测从 skip 转 pass (SteghideAdapter 9 / SteghideCrackAction 8 / SteghideExtractAction 7 跑通) | ✅ done (commit (待 push)) |
| **fix_qemu_img_friendly_error** | **`qemu_img_friendly_error`** | v0.5-qemu-img-adapter | Owner 2026-06-29 23:39 实战跑 `🖼️ qemu-img 探测 (info)` auto-run → qemu_img exit 127 + stderr `[WinError 2] 系统找不到指定的文件。` + 0 SP, Owner 看不懂没法自助装 (`extend-tools/install.ps1` 路径藏在 spec). 修: 2 adapter (qemu_img + qemu_img_extract) pre-flight `resolve_tool_binary("qemu-img")` → 找不到就 emit SP `binary_not_found` (sev=2 warning) + 中文 stderr `跑 pwsh ./extend-tools/install.ps1 静默装 qemu-img; 完成后重试` + metadata `install_hint`. qemu_img_extract 写盘前预检, 避免 mkdir 空目录后跑崩. 实战 1 道同类 (flag.vmdk) **不升架构** (per §5.2), 仅改 adapter 层, 不动 base.py 普适 stderr. +3 单测 + Owner 2026-06-30 00:15 手工装 v11.0.50 到 `extend-tools/bin/win-x64/qemu/` + e2e test_qemu_img.py 13/13 PASS + tools.md §6.1 #23 #24 同步 | ✅ done (main: 待 push) |
| **fix_decoder_registry_pyc_magic** | **`decoder_registry_pyc_magic`** | v0.5-pyc-magic-sniffer + v0.5-lsb-byte-stream-extract | Owner 2026-07-01 00:24 实战拖入 `flag.pyc` (Python 2.7, 755B) → auto-run 跑完 → GUI 点 "🐍 Pyc 反编译" → DecodeRunner 报 `ValueError: unknown decoder: pyc_decompiler`. 根因: v0.5-lsb-byte-stream-extract + v0.5-pyc-magic-sniffer 加新 decoder (`magic_sniffer` + `pyc_decompiler`) 时**只**在 `__main__.py:319-322` 显式 import 触发 CLI 路径, **漏**了 `core/decoders/__init__.py:26-30` side-effect import → GUI 路径走 `main_window.py:21` 触发不到 → registry 没这 2 个 → "unknown decoder". 修: `core/decoders/__init__.py` 加 2 行 side-effect import + `__all__` 同步 + `tests/unit/gui/test_text_only_decoders.py::EXPECTED_FILE_BASED_DECODERS` 同步加 magic_sniffer + pyc_decompiler + 加 2 个回归 case (`test_registry_contains_magic_sniffer_and_pyc_decompiler` + `test_decoder_init_side_effect_imports_v0_5_decoders`). 同类 bug 历史: `main_window.py:14` 注释里 coords-qr 当时只修了单点. 实战 1 道同类 (flag.pyc) **不升架构** (per §5.2), 仅修 side-effect import. +2 单测, GUI 启动 registry 42 → 44 (pyc_decompiler + magic_sniffer) | ✅ done (commit (待 push)) |

---

## v0.5-gui-zip-full — GUI auto-run DAG trigger 走 zip-full

**详细记录**：[`upgrade/fix_gui_zip_trigger_no_bruteforce.md`](upgrade/fix_gui_zip_trigger_no_bruteforce.md)（TODO: 待补充 — 历史 fix 详细记录缺失, 后续 v0.5+ 补齐）

## v0.5-base64-image-file-windows — base64-image decoder Win 端 file 命令找不到

**详细记录**：[`upgrade/fix_base64_image_file_windows.md`](upgrade/fix_base64_image_file_windows.md)

## v0.5-resolve-tool-binary-subdir — resolve_tool_binary 加 subdir fallback

**详细记录**：[`upgrade/fix_resolve_tool_binary_subdir.md`](upgrade/fix_resolve_tool_binary_subdir.md)

---

## fix_decoder_registry_pyc_magic — v0.5+ 新 decoder 漏 `__init__.py` side-effect import

**详细记录**：[`upgrade/fix_decoder_registry_pyc_magic.md`](upgrade/fix_decoder_registry_pyc_magic.md)（2026-07-01 00:35 Owner 实战 flag.pyc 触发）

**沉淀 checklist**（per §5.4 + §5.2 实战 ≥3 道同类再升架构，目前**不**并入 AGENTS）：
1. 新建 `core/decoders/<name>.py` + `register_decoder(DecoderSpec(...))`
2. **必须**在 `core/decoders/__init__.py` 加 side-effect import（GUI 路径）
3. **必须**在 `__main__.py` 加 side-effect import（CLI 路径）
4. **必须**更新 `tests/unit/gui/test_text_only_decoders.py::EXPECTED_FILE_BASED_DECODERS` 或 `EXPECTED_TEXT_ONLY_DECODERS`
5. 加单测覆盖 `get_decoder(name) is not None`
