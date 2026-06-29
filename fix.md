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

---

## v0.5-gui-zip-full — GUI auto-run DAG trigger 走 zip-full

**详细记录**：[`upgrade/fix_gui_zip_trigger_no_bruteforce.md`](upgrade/fix_gui_zip_trigger_no_bruteforce.md)（TODO: 待补充 — 历史 fix 详细记录缺失, 后续 v0.5+ 补齐）

## v0.5-base64-image-file-windows — base64-image decoder Win 端 file 命令找不到

**详细记录**：[`upgrade/fix_base64_image_file_windows.md`](upgrade/fix_base64_image_file_windows.md)

## v0.5-resolve-tool-binary-subdir — resolve_tool_binary 加 subdir fallback

**详细记录**：[`upgrade/fix_resolve_tool_binary_subdir.md`](upgrade/fix_resolve_tool_binary_subdir.md)
