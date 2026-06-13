# fix_gui_zip_trigger_no_bruteforce.md

> **fix ID**：`v0.5-gui-zip-full`
> **创建时间**：2026-06-13 22:44
> **状态**：✅ done
> **触发**：Owner 实测 `automisc-gui` + Challenge/QR_code.png
> **关联任务行**：[`prd.md §4.2 v0.5-LSB-router-GUI`](../prd.md) + [`upgrade/v0.5-LSB-router.md`](../upgrade/v0.5-LSB-router.md)

---

## 现象

`automisc-gui` 拖入 `Challenge/QR_code.png`：
- auto-run 跑 top 5 推荐（含 binwalk）
- binwalk 检测到 `ZIP archive @ offset 471`
- **`[DAG] running zip_chain on 00000000.zip`** 触发 zip chain
- step 1 try_unzip FAIL（真加密）
- step 2 fix_pseudo_encryption FAIL（真伪加密识别正确）
- **链终止 — 没 bruteforce step**

CLI 跑 `--chain zip-full`（含 bruteforce）能拿 flag `CTF{vjpw_wnoei}`（密码 7639）。**GUI 同图永远拿不到**。

## Root cause

`src/automisc/gui/main_window.py:281`：
```python
dag: DAG = build_zip_chain_dag()  # 只有 try_unzip + fix_pseudo, 无 bruteforce
```

`_maybe_trigger_zip_chain_from_binwalk` 是 v0.5-DAG-chain 早期手写代码（commit `31fe17a` 前），那时候 zip_chain 还没拆出 "zip" / "zip-full" 两个 chain。后续 CLI 已经支持 `--chain zip-full`，但 GUI 这条手写路径**没同步更新**。

## 修复

```python
# 之前
dag: DAG = build_zip_chain_dag()  # 永远无 bruteforce

# 现在
dag: DAG = build_zip_chain_with_bruteforce()  # 含 try_unzip + fix_pseudo + bruteforce
```

**额外增强**：zip 解压后扫 `extracted_to/` 目录，**自动找 `flag{/CTF{` 模式**，命中走 `append_flag_candidate` 红底高亮。

```python
# 解压后扫描
if extracted_path.is_dir():
    for f in extracted_path.rglob("*"):
        if f.is_file():
            try:
                content = f.read_text(errors="replace")
                if "flag{" in content or "CTF{" in content:
                    self.output_view.append_flag_candidate(
                        content.strip()[:200],
                        channel=f"zip_chain/{f.name}",
                    )
            except Exception:
                pass
```

## 验证

**端到端实测**（Owner GUI 路径模拟）：
```
[DAG] running zip-full chain on 00000000.zip (含 bruteforce)...
  [1] try_unzip: zip is encrypted
  [2] fix_pseudo_encryption: fix failed, restored from backup
  [3] bruteforce_zip: FOUND password='7639' (tried 7640/8421616)
[!!! FLAG CANDIDATE !!!] CTF{vjpw_wnoei}  (channel=zip_chain/4number.txt)
```

**测试套件**：`pytest tests` → **344 passed**（无回归）

## 影响范围

- **修复前**：GUI auto-run + binwalk 检测到 zip → 真加密永远 fail（用户得手动走 Chain 菜单 → zip-full）
- **修复后**：GUI auto-run + binwalk 检测到 zip → 跑 zip-full（含 bruteforce）→ 自动出 flag

## v0.5+ 改进方向

- **`recursive=True`** 通用递归链（foremost 抽出后自动接 zip chain）—— 避免 GUI 重复写 `_maybe_trigger_zip_chain_from_binwalk` 这种 ad-hoc 路径
- **auto-run 策略**：top 5 + chain 自动调度（不是仅 top 5 + 单一 trigger）
