# fix.md — 修复记录索引

> **维护策略**（per `AGENTS.md §6.1`）：只列已 merge 的 fix。  
> 单 fix 详细记录 → `fix_<bug_name>.md`（永久保留，git blame / audit 用）。  
> 未做 / TODO → 走 `prd.md §3` 任务看板，**不进** `fix.md`。

| fix ID | bug_name | 关联任务行 | 一句话描述 | 状态 |
|---|---|---|---|---|
| v0.5-gui-zip-full | `gui_zip_trigger_no_bruteforce` | v0.5-LSB-router-GUI | GUI `_maybe_trigger_zip_chain_from_binwalk` 走 `build_zip_chain_dag`（无 bruteforce）→ 真加密 zip 永远 fail | ✅ done (commit (待 push)) |

---

## v0.5-gui-zip-full — GUI auto-run DAG trigger 走 zip-full

**详细记录**：[`fix_gui_zip_trigger_no_bruteforce.md`](fix_gui_zip_trigger_no_bruteforce.md)
