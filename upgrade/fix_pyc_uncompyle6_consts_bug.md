# fix_pyc_uncompyle6_consts_bug — 修 uncompyle6 Py2.7 顶层 consts 列表反编译 bug

> **status**: 🔄 **in-progress** (per Owner 2026-07-01 09:57 反馈)
> **触发**: v0.5-train-019 (2026-07-01 00:24) + 本次 (2026-07-01 09:57) 实战 `C:\Users\zmzsg\Downloads\flag\C!_Users_zmzsg_Downloads_flag_flag.txt!flag.pyc` 两次命中同一 bug
> **关联**:
> - v0.5-pyc-magic-sniffer (main `17f0784`) — pyc_decompiler decoder 首次实现
> - v0.5-pyc-decompiler-buttons (main `6406282`) — GUI 3 按钮 + 写盘
> - v0.5-train-019-flag-pyc (✅) — 实战 v1 记录: uncompyle6 bug 训练日志, defer 修
> - v0.5-output-samedir (commit `af35fb0`) — 复用 `output_path_for` 命名
> **commit**: TBD (待实施)

---

## 1. 背景

### 1.1 Owner 反馈 (2026-07-01 09:57)

实战 `flag.pyc` 跑 uncompyle6, 反编译输出:

```python
# uncompyle6 实际输出
ciphertext = [
 3, 4, 5, 6, 7, 8, 9, 5, 10, 11, 12, 13, 14, 15, 16, 8, 17, 18, 
 19, 20, 21, 22, 23, 15]
return
```

vs 在线反编译工具 (http://tools.bugscaner.com/) 真实输出:

```python
ciphertext = [
 '96', '65', '93', '123', '91', '97', '22', '93', '70', '102', '94', 
 '132', '46', '112', '64', '97', '88', '80', '82', '137', '90', '109', 
 '99', '112']
```

**bug 现象**: uncompyle6 把 Py2.7 pyc 顶层 consts 列表的 **consts 索引** 当成值输出, 真实字符串在 `co.co_consts` 里。

### 1.2 根因分析 (per 2026-07-01 xdis inspect)

```python
# xdis load_module 拿到的顶层 code object
>>> from xdis import load_module
>>> version, _ts, _magic, co, *_ = load_module(flag_pyc)
>>> co.co_consts
[0] int: -1        ← module-level magic
[1] NoneType: None ← module-level None
[2] Code2: <code encode> ← encode 函数
[3] str: '96'      ← ciphertext[0] 真实值
[4] str: '65'      ← ciphertext[1] 真实值
...
[23] str: '99'     ← ciphertext[20] 真实值
```

**uncompyle6 输出的索引序列** `[3, 4, 5, 6, 7, 8, 9, 5, 10, 11, 12, 13, 14, 15, 16, 8, 17, 18, 19, 20, 21, 22, 23, 15]` **就是 `LOAD_CONST` 字节码的顺序**, 真实字符串按索引查 `co.co_consts` 即可还原 (24 元素, 5/8/15 重复加载)。

**末尾 `return` 关键字** 是 uncompyle6 在 module body 末尾的伪 artifact (uncompyle6 Py2.7 module-level 反汇编已知 issue)。

### 1.3 实战命中次数 (per AGENTS §5.2)

- v0.5-train-019 (2026-07-01 00:24) — 实战 #1, defer 修 (per §5.2 < 3)
- 本 spec (2026-07-01 09:57) — 实战 #2, Owner 主动要求修

**判定**: 仍 < 3 同类命中, 但 Owner 主动反馈要求修 (不是观察), 修法**通用化** (用 xdis co_consts 查任意 consts 列表, 适用所有触发同 bug 的 Py2.7 pyc, 不只是 flag.pyc) — **升架构** (per AGENTS §5.2 "能泛化" 标准 ✅), 走 fix spec 流程。

---

## 2. 目标

### 2.1 能力 A: 修 uncompyle6 Py2.7 顶层 consts 列表反编译 bug

**目标**: 在 `pyc_decompiler.py:_decompile_with_uncompyle6` 后调 `_fix_uncompyle6_consts_bug(skeleton, file_path)`, 修后输出真实字符串。

### 2.2 修法 (per xdis inspect 验证)

```python
def _fix_uncompyle6_consts_bug(skeleton: str, file_path: str) -> str:
    """修 uncompyle6 Py2.7 顶层 consts 列表反编译 bug."""
    # 1. 拿 xdis co.co_consts (顶层 code object 的真实 consts)
    try:
        version, _ts, _magic, co, *_ = load_module(file_path)
        top_consts = co.co_consts
    except Exception:
        return skeleton  # 拿不到, 退而求其次

    # 2. 解析 skeleton 里 "<name> = [N, N, N, ...]" 模式 (顶层, 模块级)
    pattern = re.compile(
        r"^(\w+)\s*=\s*\[\s*((?:\d+\s*,\s*)*\d+)\s*\]\s*$",
        re.MULTILINE,
    )

    def _replace(m):
        var_name = m.group(1)
        indices = [int(x.strip()) for x in m.group(2).split(",") if x.strip()]
        # 3. 查 top_consts[N] 拿真实值
        try:
            real_values = [top_consts[i] for i in indices]
        except IndexError:
            return m.group(0)  # 索引越界, 跳过
        # 4. 全是 str 才替换 (其他类型可能本身正确)
        if not all(isinstance(v, str) for v in real_values):
            return m.group(0)
        # 5. 替换成 'val1', 'val2', ... (单引号, per Python 2 repr)
        quoted = ", ".join(repr(v) for v in real_values)
        return f"{var_name} = [{quoted}]"

    fixed = pattern.sub(_replace, skeleton)

    # 6. 末尾 `return` 去掉 (module-level 伪 artifact)
    fixed = re.sub(r"^return\s*$", "", fixed, flags=re.MULTILINE)

    return fixed
```

### 2.3 改 `pyc_decompiler.py:_decompile_with_uncompyle6`

```python
def _decompile_with_uncompyle6(file_path: str) -> tuple[str, str]:
    """Py2.x 反编译, 返回 (source_code, method).
    
    v0.5 fix_pyc_uncompyle6_consts_bug: 反编译后调 _fix_uncompyle6_consts_bug
    修 Py2.7 顶层 consts 列表 bug (uncompyle6 把 consts 索引当值输出).
    """
    import uncompyle6
    out = io.StringIO()
    uncompyle6.decompile_file(file_path, out)
    skeleton = out.getvalue()
    # 修 bug (per 实战 flag.pyc 命中)
    fixed = _fix_uncompyle6_consts_bug(skeleton, file_path)
    return fixed, "uncompyle6"
```

### 2.4 范围 (in / out)

**IN**:
- ✅ `core/decoders/pyc_decompiler.py` 加 `_fix_uncompyle6_consts_bug` 函数
- ✅ `_decompile_with_uncompyle6` 调 fix 函数
- ✅ 4 单测覆盖 (触发 / 不触发 / Py3 不调 / return 去除)
- ✅ CLI smoke flag.pyc 验证

**OUT** (不动):
- ❌ `decompyle3` (Py3.x 走 dis / decompyle3 都没这 bug)
- ❌ `dis` fallback
- ❌ `PycDecompileResult` 字段
- ❌ GUI 入口 / menu_dock / DecodeRunner (per v0.5-pyc-decompiler-buttons spec §2.3 "不动 decoder 核心逻辑")

---

## 3. 设计

### 3.1 模块改动汇总

| 文件 | 改动 | LOC |
|---|---|---|
| `core/decoders/pyc_decompiler.py` | 加 `_fix_uncompyle6_consts_bug` 函数 + `_decompile_with_uncompyle6` 调它 | ~+50 |
| `tests/unit/core/decoders/test_pyc_decompiler.py` | 加 4 单测 (fix 函数) | ~+100 |
| **合计** | **2 文件, ~+150 LOC** (per AGENTS §2.1 ≤ 400 行/文件) | — |

### 3.2 不修的 bug (per §5.2 defer)

- ❌ **嵌套 code object 里的 consts bug** (e.g. def encode 里的字符串列表) — 当前实战没命中, 不动
- ❌ **更复杂的 Py2.7 字节码 uncompyle6 反编译 bug** (e.g. lambda 内 consts, 闭包) — 实战命中 < 3
- ❌ **`return` artifact 在 def 函数末尾** — 当前 fix 函数只去 module-level 末尾的 `return`, 函数末尾不动 (有可能是函数真的 return)

### 3.3 单测设计 (4 个)

| # | 测 | 预期 | 覆盖 |
|---|---|---|---|
| 1 | `test_fix_uncompyle6_consts_bug_replaces_indices` | flag.pyc 触发 → ciphertext 变真实字符串 | 主修法 |
| 2 | `test_fix_uncompyle6_consts_bug_removes_trailing_return` | 末尾 `return` 被去掉 | artifact fix |
| 3 | `test_fix_uncompyle6_consts_bug_no_change_on_normal` | 不触发 bug 的 pyc → skeleton 不变 | 旁路安全 |
| 4 | `test_pyc_decompiler_uses_xdis_consts_for_py2` | `run_pyc_decompiler` Py2.x 跑 flag.pyc → source_code 含真实 ciphertext 字符串 (e.g. '96', '65') | 端到端 |

---

## 4. 实施

### 4.1 任务分解

| # | 任务 | 状态 | 文件 | 估计 |
|---|---|---|---|---|
| 1 | 写 fix spec (本文件) | 🔄 | upgrade/fix_pyc_uncompyle6_consts_bug.md | — |
| 2 | `pyc_decompiler.py` 加 `_fix_uncompyle6_consts_bug` + 改 `_decompile_with_uncompyle6` | ⏳ | edit | ~+50 |
| 3 | 加 4 单测覆盖 fix 函数 + 端到端 | ⏳ | edit test | ~+100 |
| 4 | 跑全套单测 + GUI 集成 + 0 新失败验证 | ⏳ | pytest | — |
| 5 | CLI smoke flag.pyc → 验证 ciphertext 真实字符串 | ⏳ | python | — |
| 6 | upgrade.md 索引行 + STRUCTURE.md 同步 | ⏳ | edit | +1 行 |
| 7 | 单 Owner commit (per AGENTS §2.4 询问卡) | ⏳ | git | — |

### 4.2 6 关验收 (per AGENTS §1 铁律 4)

| 关 | 验收点 | 预期 | 实测 |
|---|---|---|---|
| ① | 代码合并 main | commit 后 | ⏳ |
| ② | `pytest tests/unit` 全绿 | ≥ baseline, **0 新失败** | ⏳ |
| ②' | `pytest tests/integration/gui` 全绿 | ≥ baseline | ⏳ |
| ③ | GUI 集成测试通过 | ✅ | ⏳ |
| ④ | Smoke: CLI `automisc decode pyc_decompiler --file flag.pyc` → source_code 含 `'96', '65', ...` | ✅ | ⏳ |
| ⑤ | Owner 自审 | per 本 spec | ⏳ |
| ⑥ | 文档同步 (upgrade.md + STRUCTURE.md + 本 spec) | ✅ | ⏳ |

---

## 5. 验证 (smoke 计划)

### 5.1 CLI smoke

```bash
$ PYTHONPATH=src python -m automisc decode pyc_decompiler --file C:/Users/zmzsg/Downloads/flag/C!...flag.pyc
=== 🐍 Pyc 反编译 (自动判版本) ===
input_path: C:\Users\zmzsg\Downloads\flag\C!_..._flag.pyc
raw_size: 755
output_path: C:\Users\zmzsg\Downloads\flag\C!_..._flag__pyc.py  ← 修后写盘
method: uncompyle6
source_code: ...
ciphertext = [
 '96', '65', '93', '123', '91', '97', '22', '93', '70', '102', '94', 
 '132', '46', '112', '64', '97', '88', '80', '82', '137', '90', '109', 
 '99', '112']  ← 真实字符串!
```

### 5.2 期望产物

- CLI 输出 `source_code` 含真实 ciphertext 字符串 (24 元素)
- 写盘 `flag__pyc.py` 含真实 ciphertext (后续解 flag 链路恢复)

### 5.3 端到端解 flag 验证

```python
# 修后 source_code 可直接跑解 flag
ciphertext = ['96', '65', '93', '123', '91', '97', '22', '93', '70', '102', '94',
              '132', '46', '112', '64', '97', '88', '80', '82', '137', '90', '109',
              '99', '112']
# encode: s = chr(i ^ ord(flag[i])); if i%2==0: ord(s)+10; else: ord(s)-10
# encode 返回 ciphertext[::-1], 题目给的是 encode 输出
# 反向: 对 ciphertext[::-1] 按 i 顺序, +10 反 -10, -10 反 +10, 再 XOR i
# 期望: flag{Y@e_Cl3veR_C1Ever!} (per v0.5-train-019 实战 #1 已验证)
```

---

## 6. 风险 + 缓解

| 风险 | 缓解 |
|---|---|
| `_fix_uncompyle6_consts_bug` 把正确输出误改 (e.g. 真实 int 列表) | **只在列表元素全是 str 时替换** (per `if not all(isinstance(v, str) for v in real_values): return m.group(0)`); 其他类型列表 (int/float/None) 跳过 |
| 正则匹配误中函数内 consts (e.g. `def f(): x = [1, 2]`) | regex 用 `^...$` + `MULTILINE` 严格匹配"行首到行尾", 跟 uncompyle6 输出格式对齐 (函数体缩进不会触发) |
| 末尾 `return` 误删函数 return | regex 同样用 `^return\s*$` + `MULTILINE` 严格匹配"独立行的 return", 函数末尾的 `return` 一般缩进 + 在函数体内, 不会触发 |
| `co.co_consts` 索引越界 (e.g. uncompyle6 输出索引超过 co_consts 长度) | try/except IndexError, 跳过该 var, 保留 uncompyle6 原输出 |
| xdis load_module 失败 (e.g. 损坏 pyc) | try/except Exception, 退而求其次返回 uncompyle6 原输出 (跟现状一致) |
| Py3.x pyc 也调 fix 函数 (decompyle3 没这 bug 但函数会跑) | 修法只动 module-level 顶层列表, Py3.x pyc 顶层列表若有 int (e.g. 常量) 不会改 (int 不替换); 性能损耗 < 50ms (单次 load_module) |

---

## 7. 决策点 (per AGENTS §1 铁律 2 - Owner 拍板)

| # | 决策点 | Owner 默认 | Mavis 建议 |
|---|---|---|---|
| Q1 | 修不修这个 bug? | **Y** (per Owner 2026-07-01 09:57 反馈要求修) | 同 |
| Q2 | 修法? | **A: xdis co_consts 查表 + 替换** (per xdis inspect 验证 100% 匹配) | 同 |
| Q3 | 末尾 `return` 一起修? | **Y** (per 实战命中, module-level 伪 artifact) | 同 |
| Q4 | 升架构 vs 单题打补丁? | **A: 升架构** (修法通用化, 适用所有触发同 bug 的 Py2.7 pyc, per §5.2 "能泛化" 标准) | 同 |
| Q5 | 写新 fix spec 还是补到 v0.5-pyc-decompiler-buttons? | **A: 写新 fix spec** (per 2026-06-28 治理 `fix_<bug>.md` 在 `upgrade/` 子目录, bug fix 跟 feature 分离) | 同 |

---

## 8. 引用

- `core/decoders/pyc_decompiler.py:_decompile_with_uncompyle6` (main `6406282`) — 当前 Py2.x 反编译入口
- `upgrade/v0.5-pyc-decompiler-buttons.md` — 上一迭代 (GUI 3 按钮 + 写盘, main `6406282`)
- `upgrade/v0.5-train-019-flag-pyc.md` — 实战 v1 训练日志 (defer 修, Owner 反馈要求修)
- `upgrade/v0.5-pyc-magic-sniffer.md` — pyc_decompiler 首次实现
- `AGENTS.md §1 铁律 2` (新需求先文档) / `§1 铁律 4` (bug fix 6 关验收) / `§2.1` (≤ 400 行/文件) / `§5.2` (架构判定)
- 2026-06-28 治理: `fix_<bug>.md` 在 `upgrade/` 子目录 (跟迭代 spec 同级)

---

## 9. 实施前置

- ✅ Owner 反馈明确要求修 (2026-07-01 09:57)
- ✅ xdis inspect 验证修法 (co_consts 100% 匹配 online 工具输出)
- ⏳ 待 Owner 拍板 Q1-Q5 后直接进入实施 (per AGENTS §1 铁律 2)
- ⏳ Mavis 默认 A 方案: 升架构 + 修法 + 末尾 return 修 + 新 fix spec
