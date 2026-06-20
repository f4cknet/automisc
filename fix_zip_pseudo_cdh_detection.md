# fix_zip_pseudo_cdh_detection — 伪加密「CDH 形态」漏识别 bug 修复

> **status**: 🚧 in-progress (2026-06-20)
> **触发**: `upgrade/v0.5-train-004-cdh-pseudo-detect.md`（Owner 报告 2026-06-20）
> **关联 fix**: `fix_gui_zip_trigger_no_bruteforce.md`（同模块）
> **关联 upgrade**: `v0.5-train-002-zip-pseudo-175b`（v0.5 训练驱动第 2 篇，形态 C）

---

## 1. 背景

zip 标准规定 LFH (Local File Header) + CDH (Central Directory Header) 都有 encryption flag bit (general purpose bit flag offset 0, bit 0)。zipfile / 7z / unzip 等**所有标准实现**都读 **CDH** 判定加密（CDH 是 entry 的"官方属性"）。

**伪加密变体**（per `v0.5-train-004` §5）：

| 形态 | LFH bit0 | CDH bit0 | 现有检测 | 现有修复 |
|---|---|---|---|---|
| A | 1 | 0 | ✅ | ✅ |
| **B** | **0** | **1** | ❌ | ❌（检测不到就不跑）|
| C | 1 | 1 | ✅ | ✅ |

**owner 2026-06-20 命中形态 B**——是 foremost / 工具雕 zip 时最常出现的"工具友好型"伪加密（只改 CDH，LFH 留明文方便后续工具解压）。

---

## 2. 根因（per §3.3 train-004）

`src/automisc/core/actions/zip_chain.py:30-61` `_is_pseudo_encrypted` **只扫 LFH**：

```python
i = 0
while i < len(data) - 4:
    if data[i:i+4] == b"PK\x03\x04":  # ← LFH
        flag = struct.unpack("<H", data[i+6:i+8])[0]
        if not (flag & 0x1):
            return False  # ← 形态 B 死在这
```

**好消息**：`FixPseudoEncryptionAction.run` 修复代码（line 152-167）**已经会同时清 LFH + CDH 的 bit 0**——只要 `_is_pseudo_encrypted` 放它过就行。

---

## 3. 修复设计

### 3.1 升级 `_is_pseudo_encrypted` 扫 CDH

**算法**：
1. **第一遍**：扫所有 LFH，建 `fname → (flag, comp_size, data_start)` map
2. **第二遍**：扫所有 CDH，找 CDH bit0=1 的 entry：
   - 若 LFH bit0=0 → **形态 B**（直接判伪加密，不看 data header）
   - 若 LFH bit0=1 → 看 LFH 的 `data_start + 11` 字节，不在 0-11 范围 → 伪加密（形态 A/C 逻辑保留）
3. **任一 entry 命中** → True

**为什么形态 B 不看 data header**：因为 LFH bit0=0 时**没有真加密**，data 一定是明文，根本不可能有 PKCS#5 header。直接判伪加密。

### 3.2 不动的部分

- `FixPseudoEncryptionAction.run` line 152-167 已经修 LFH + CDH，**不动**
- `TryUnzipAction.run` line 103-114 调用 `_is_pseudo_encrypted` + 设 `encrypted=not is_pseudo`，**逻辑正确**，修了检测就修好整条链
- DAG 拓扑（try_unzip → fix_pseudo → 终止，per `core/dag.py:85-92`）**不动**
- `fix_pseudo_zip` chain 工具栏入口（per `core/chains.py:24`）**不动**

### 3.3 修复代码预览

```python
def _is_pseudo_encrypted(zip_path: Path) -> bool:
    """检测 zip 是否伪加密 (LFH/CDH 任一 bit0=1 但内容无真加密 header).

    覆盖 3 形态:
    - A: LFH=1, CDH=0 (仅 LFH 假加密)
    - B: LFH=0, CDH=1 (仅 CDH 假加密) ← zipfile 读 CDH 判定
    - C: LFH=1, CDH=1 (双假加密)

    真加密特征: LFH bit0=1 + data 起始 12 字节末位在 0-11 (PKCS#5 header)
    """
    try:
        with open(zip_path, "rb") as f:
            data = f.read()
    except OSError:
        return False

    # 1) 收所有 LFH
    lfh_map: dict[str, tuple[int, int, int]] = {}  # fname → (flag, comp_size, data_start)
    i = 0
    while i < len(data) - 4:
        if data[i:i+4] == b"PK\x03\x04":
            fname_len = struct.unpack("<H", data[i+26:i+28])[0]
            extra_len = struct.unpack("<H", data[i+28:i+30])[0]
            comp_size = struct.unpack("<I", data[i+18:i+22])[0]
            flag = struct.unpack("<H", data[i+6:i+8])[0]
            fname = data[i+30:i+30+fname_len].decode("utf-8", errors="replace")
            data_start = i + 30 + fname_len + extra_len
            lfh_map[fname] = (flag, comp_size, data_start)
            i = data_start + comp_size
        else:
            i += 1

    # 2) 扫 CDH: 找 bit0=1 的 entry
    i = 0
    while i < len(data) - 4:
        if data[i:i+4] == b"PK\x01\x02":
            fname_len = struct.unpack("<H", data[i+28:i+30])[0]
            extra_len = struct.unpack("<H", data[i+30:i+32])[0]
            comment_len = struct.unpack("<H", data[i+32:i+34])[0]
            flag_cdh = struct.unpack("<H", data[i+8:i+10])[0]
            fname = data[i+46:i+46+fname_len].decode("utf-8", errors="replace")
            if flag_cdh & 0x1 and fname in lfh_map:
                flag_lfh, comp_size, data_start = lfh_map[fname]
                # 形态 B: LFH bit0=0, CDH bit0=1 → 直接判伪加密
                if not (flag_lfh & 0x1):
                    return True
                # 形态 A/C: LFH bit0=1 → 看 data 是否有真加密 PKCS#5 header
                if comp_size < 12:
                    return True
                if data[data_start + 11] not in range(12):
                    return True
            i = i + 46 + fname_len + extra_len + comment_len
        else:
            i += 1

    return False
```

### 3.4 单测设计

**新增 3 个 fixture + 3 个 test**（覆盖 3 形态）：

| Fixture | LFH bit0 | CDH bit0 | 期望 |
|---|---|---|---|
| `pseudo_zip_form_a` | 1 | 0 | `_is_pseudo_encrypted` = True |
| `pseudo_zip_form_b` | 0 | 1 | `_is_pseudo_encrypted` = True ← **owner 这题** |
| `pseudo_zip_form_c` | 1 | 1 | `_is_pseudo_encrypted` = True（**现有 `pseudo_zip` fixture 重命名**）|

`fix_pseudo` 单测也加 3 个，验证修后能正常解压。

---

## 4. 范围 (in / out)

**in**:
- 改 `_is_pseudo_encrypted` 算法（同时扫 LFH + CDH）
- 改 `pseudo_zip` fixture → `pseudo_zip_form_c`（更明确）
- 新增 `pseudo_zip_form_a` + `pseudo_zip_form_b` fixture
- 加 3 个 `_is_pseudo_encrypted` 单测
- 加 3 个 `FixPseudoEncryptionAction` 单测
- 实测 owner 真实样本

**out**:
- **不动** `FixPseudoEncryptionAction.run`（修复代码已对 LFH+CDH）
- **不动** `TryUnzipAction.run`（检测修好就修好整条链）
- **不动** DAG 拓扑 / chain 模板
- **不动** GUI 入口 / 工具栏按钮

---

## 5. 验证标准（per 铁律 4）

1. **pytest 全绿**（修后跑 `pytest -m "not integration" -q`，应 ≥ 660 passed，原 669 passed + 6 新 = ~675 passed）
2. **GUI 集成测试**（`pytest -m integration` 跑通）
3. **owner 真实样本 smoke**：
   ```bash
   $ python3 -c "
   import sys; sys.path.insert(0, 'src')
   from automisc.core.actions.zip_chain import _is_pseudo_encrypted
   print('is_pseudo:', _is_pseudo_encrypted(
       '/Users/minzhizhou/Downloads/output/zip/00000038.zip'
   ))
   "
   # 期望: True
   ```
4. **owner 真实样本 端到端**：跑 `FixPseudoEncryptionAction` → 验证能解出 `asd/good-已合并.jpg`
5. **owner 自审**（单 Owner）
6. **文档同步**：本 fix_*.md + fix.md + upgrade.md + STRUCTURE.md（如需）

---

## 6. 任务分解

| 步骤 | 状态 | 备注 |
|---|---|---|
| 1. 写训练日志 v0.5-train-004 | ✅ done | 见 upgrade/ 目录 |
| 2. 写本 fix 文档 | 🚧 in-progress | — |
| 3. 改 `_is_pseudo_encrypted` | ⏳ pending | per §3.3 代码预览 |
| 4. 加 3 形态 fixture + 6 单测 | ⏳ pending | `tests/unit/core/actions/test_dag.py` |
| 5. pytest 全跑 | ⏳ pending | 验证 |
| 6. 实测 owner 真实样本 | ⏳ pending | `~/Downloads/output/zip/00000038.zip` |
| 7. fix.md + upgrade.md 加索引 | ⏳ pending | — |
| 8. 询问卡走 commit | ⏳ pending | per AGENTS §2.4 v1.20 |
| 9. 询问卡走 push | ⏳ pending | per AGENTS §2.4 v1.20 |

---

## 7. 待 Owner 拍板的决策点

**无新决策点**——按 owner 铁律「修 bug 不脑补」：

- 形态 B 不看 data header 直接判伪加密（**有依据**：LFH bit0=0 时 data 必然明文，无 PKCS#5 header）
- 3 形态都归「伪加密」一档，journal 不细分 (per `v0.5-train-004 §6` 末行建议「后续可加 pseudo_form 字段」但**不在本 fix 范围**)

---

## 8. 引用

- AGENTS.md §1 铁律 1-5（文档优先 / 任务有状态 / 未验证=未完成）
- AGENTS.md §5.3 训练会话标准动作
- `upgrade/v0.5-train-004-cdh-pseudo-detect.md`（owner 报告根因）
- `src/automisc/core/actions/zip_chain.py:30-61`（现有检测实现）
- `tests/unit/core/actions/test_dag.py:38-51`（现有 `pseudo_zip` fixture = 形态 C）
