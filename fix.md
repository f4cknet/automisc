# fix.md — 修复记录索引

> **维护策略**（per `AGENTS.md §6.1`）：只列已 merge 的 fix。  
> 单 fix 详细记录 → `upgrade/fix_<bug_name>.md`（永久保留，git blame / audit 用）。  
> **路径修正 (2026-06-28 per Owner)**: `fix_<bug_name>.md` 应在 `upgrade/` 子目录（跟 `upgrade/v0.5-*.md` 迭代 spec 同级），不在项目根。  
> 未做 / TODO → 走 `prd.md §3` 任务看板，**不进** `fix.md`。

| fix ID | bug_name | 关联任务行 | 一句话描述 | 状态 |
|---|---|---|---|---|
| v0.5-gui-zip-full | `gui_zip_trigger_no_bruteforce` | v0.5-LSB-router-GUI | GUI `_maybe_trigger_zip_chain_from_binwalk` 走 `build_zip_chain_dag`（无 bruteforce）→ 真加密 zip 永远 fail | ✅ done (commit (待 push)) |
| v0.5-base64-image-file-windows | `base64_image_file_windows` | v0.5-base64-image | `core/decoders/base64_image.py:_file_detect` 用 `shutil.which("file")` Win 端 None → 抛 "file 检测: (empty / no file command)"；改用 `resolve_tool_binary("file")` 走 extend-tools/bin/win-x64/file.exe fallback | ✅ done (commit (待 push)) |

---

## v0.5-gui-zip-full — GUI auto-run DAG trigger 走 zip-full

**详细记录**：[`upgrade/fix_gui_zip_trigger_no_bruteforce.md`](upgrade/fix_gui_zip_trigger_no_bruteforce.md)（TODO: 待补充 — 历史 fix 详细记录缺失, 后续 v0.5+ 补齐）

## v0.5-base64-image-file-windows — base64-image decoder Win 端 file 命令找不到

**详细记录**：[`upgrade/fix_base64_image_file_windows.md`](upgrade/fix_base64_image_file_windows.md)
