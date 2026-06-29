# fix_qemu_img_friendly_error (2026-06-29 23:40)

| 字段 | 值 |
|---|---|
| **类型** | 🟢 fix（实战兜底，修 UX） |
| **触发** | Owner 实战 2026-06-29 23:39 跑 GUI `🖼️ qemu-img 探测 (info)` auto-run，发现 `qemu_img (auto FAIL)` stderr `[WinError 2] 系统找不到指定的文件。` exit_code=127 suspicious_points(0) |
| **根因** | qemu-img 未安装（per v0.5-qemu-img-extend-tools spec，写了 `extend-tools/install.ps1:qemu_img_setup_silent` 静默装但 Owner 没跑 `pwsh ./extend-tools/install.ps1`）。base.py `_run_subprocess` 捕 `FileNotFoundError` 时 stderr 写 raw 英文错误 `[WinError 2]`，未提示 装命令 + 未 emit SP，UI 全黑 |
| **实战位置** | flag.vmdk → auto-run pool 跑 qemu_img → 报错 → owner 不查 spec 不知道装哪 |
| **影响范围** | 2 个 qemu-img adapter（qemu_img info + qemu_img_extract convert）。其他 adapter 现在 binary 都在（binwalk/exiftool/file/7z/foremost/steghide/xxd 全装），同样 exit 127 路径**不**踩到（实战证据） |

## 1. Fix 决策（per AGENTS §1 铁律 2 新需求先文档 → 实战 1 道同类不升架构，per §5.2；本 fix 是修 UX 不是新增架构能力）

### 1.1 修法选型

| 候选 | 描述 | 取舍 |
|---|---|---|
| **A. Adapter 层预检** | 在 qemu_img / qemu_img_extract `run()` 第 1 步调 `resolve_tool_binary("qemu-img")`，找不到就 emit SP `binary_not_found` + return ToolResult(exit=127, stderr=友好提示)。**复用** v0.5-extend-tools 的 `resolve_tool_binary` | ✅ 选 — 实战触发 1 道同类不升架构（per §5.2）；逻辑在 adapter 单文件内可控可测 |
| **B. Base 层 `_run_subprocess` 增强** | 捕 `FileNotFoundError` 时 stderr 加装命令（所有 adapter 受益） | ❌ 不选 — 改动 base.py 全 adapter 范围，违反"实战 1 道同类不升架构"原则（base.py 是基础设施 = 架构层）；base.py 改 raw error 信息会让其他 adapter 实测 binary 在的场景看不出区别（无害但超出 scope） |
| **C. Auto-install fallback** | binary 找不到 → 自动调 `pwsh ./extend-tools/install.ps1` 静默装 | ❌ 拒 — 范围爆炸：NSIS 静默装需要管理员权限、网络下载 100MB+、silent 失败处理、sandbox 提示；实战 1 道同类不该升架构 |
| **D. Spec 只写 doc 不动 code** | 文档里写"如果 qemu-img 找不到，请先跑 install.ps1" | ❌ 拒 — Owner 实战反馈就是 UX 问题，doc 修**不**解决实战 stderr 黑屏；v0.5-qemu-img-adapter 已落地 GUI 入口，doc 不动 code 反而劣化体验 |

### 1.2 取舍佐证

**选 A 理由**：
1. 实战 1 道同类**不升架构**（per §5.2），A 是 adapter 层局部改动**不**触架构
2. A 完全复用既有 `resolve_tool_binary`，0 新基础设施
3. A 单测可控：mock binary 不在 → emit SP + exit 127；mock binary 在 → 正常跑（2 case 覆盖）
4. A 不影响 base.py：base.py 的 FileNotFoundError 兜底**保留**（其他 adapter 仍走原路径，万一 base.py 改坏了全 adapter 中招）
5. 修法跟 v0.5-qemu-img-extend-tools 决策风格一致（owner 已装 + 有 spec，按"先装再跑"约定）

**为什么不动 base.py stderr**：
- base.py 改 stderr 信息是**普适**改动（影响所有 adapter）
- 实战 1 道同类**不**足以证明"所有 adapter stderr 都该改"
- A 方案已经够 owner 实战用（adapter 预检就把 stderr 拦了，base.py 路径走不到）
- 万一未来某个 adapter binary missing 实战触发，再扩 base.py 不晚（per §5.2 实战 ≥3 道同类再升架构）

## 2. 实施

### 2.1 Adapter 改动

**qemu_img.py** 改 `run()`：
```python
def run(self, file_path: str) -> ToolResult:
    from automisc.tools.paths import resolve_tool_binary
    qemu_img_bin = resolve_tool_binary("qemu-img")
    if not qemu_img_bin:
        # qemu-img 未装兜底 (fix_qemu_img_friendly_error, 实战 UX): 友好 SP + 提示装命令
        # 同时元数据里给 install.ps1 路径, 让 GUI menu_dock 可加"一键装"按钮 (per 后续 v0.5+)
        stderr_msg = (
            "binary 'qemu-img' 未找到 (exit 127)\n"
            "提示: 跑 `pwsh ./extend-tools/install.ps1` 静默装 QEMU Win v9.1.0 "
            "(NSIS 自动加 PATH, 完成后重试)。详见 "
            "upgrade/v0.5-qemu-img-extend-tools.md"
        )
        return ToolResult(
            tool_name=self.name,
            exit_code=127,
            stdout="",
            stderr=stderr_msg,
            suspicious_points=[SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="binary_not_found",
                offset=None,
                matched_pattern="qemu-img 未安装 (exit 127)",
                severity=2,  # warning: 功能不可用, 但不是文件恶意
                suggested_action=(
                    "跑 `pwsh ./extend-tools/install.ps1` 静默装 QEMU; "
                    "或 GUI 工具栏点 '🖼️ qemu-img 转换' 之前先装"
                ),
            )],
            metadata={"binary_required": "qemu-img", "install_hint": "pwsh ./extend-tools/install.ps1"},
        )

    cmd = [qemu_img_bin, "info", file_path]
    ...
```

**qemu_img_extract.py** 同样改（binary 找不到不写盘，直接 return 同样的 1 SP + exit 127）。

### 2.2 Base.py 不动

不动 base.py _run_subprocess 的 FileNotFoundError 兜底。理由：
- A 方案**拦在** adapter，预检返回 exit 127 不走 subprocess，所以走不到 base.py catch
- 万一未来 adapter 漏写预检，base.py 的 raw stderr `[WinError 2]` 仍是兜底（够用，等实战 ≥3 道同类再升级 friendly stderr）

### 2.3 单测（tests/unit/tools/misc/archive/test_qemu_img.py 加 3 case）

```python
def test_info_emits_binary_not_found_sp_when_missing():
    """qemu-img 未装: 友好 SP + 中文 stderr + 装命令 hint (per fix_qemu_img_friendly_error)."""
    with patch("automisc.tools.misc.archive.qemu_img.resolve_tool_binary", return_value=None):
        result = QemuImgAdapter().run("/tmp/flag.vmdk")
    assert result.exit_code == 127
    assert any(sp.category == "binary_not_found" for sp in result.suspicious_points)
    assert "install.ps1" in result.stderr

def test_extract_emits_binary_not_found_sp_when_missing():
    """qemu_img_extract 未装: 同样兜底 + 写盘前预检, 不写任何目录."""
    with patch("automisc.tools.misc.archive.qemu_img_extract.resolve_tool_binary", return_value=None):
        result = QemuImgExtractAdapter().run("/tmp/flag.vmdk")
    assert result.exit_code == 127
    assert any(sp.category == "binary_not_found" for sp in result.suspicious_points)
    # 验证不写空目录 (跟原七个 qemu_img_extract 行为一致)
    assert not any(Path("/tmp").glob("*qemu_img_raw*"))

def test_info_falls_through_to_subprocess_when_binary_found():
    """qemu-img 装着: 走真 subprocess (exit 0 mock) 仍正常 emit vdisk_format SP."""
    # mock resolve_tool_binary 真 found + mock _run_subprocess 返回 vmdk format
    ...
```

## 3. 验证

- 单测 test_qemu_img.py 加 3 case (全过)
- 回归 tests/unit/tools/misc/archive/ 全过
- 实战: owner GUI 跑 `🖼️ qemu-img 探测 (info)` flag.vmdk → stderr 输出 `binary 'qemu-img' 未找到... 跑 pwsh ./extend-tools/install.ps1...` 友好提示

### 3.2 ✅ Owner 实战装完 (per 2026-06-30 00:15)

**装法**: Owner 手工装 `extend-tools/bin/win-x64/qemu/qemu-img.exe` v11.0.50
(URL `qemu-w64-setup-2025.05.12.exe` install.ps1 失效 — Stefan Weil 站点
2026-04-22 后改命名 11.0.0 后的 installer `qemu-w64-setup-2026*.exe` 链路
需要 install.ps1 §82 URL 更新, **实战 ≥3 道同类再评估升架构** 不并入本 fix)
+ 走 `paths.py` 第 4 级异名 subdir fallback 自动找到 (extend-tools/bin/win-x64/
  下任何 1 层 subdir/<name>.exe), 不需要 PATH 注册.

**e2e 激活验证**:
- `test_qemu_img.py::TestQemuImgE2E::test_qemu_img_info_real_binary_does_not_panic` 从 skip → PASS (13/13 全过)
- fixture autouse 加 `if "real_binary" in request.node.name: return` 让 e2e 走真 binary
- `HAS_QEMU_IMG` 改用 `resolve_tool_binary` 而非 `shutil.which` (paths.py 4 级 fallback 一致)

**实战命令验证** (per Owner 反馈"你继续"):
```
> qemu-img --version
qemu-img version 11.0.50 (v11.0.0-12631-g54e84cdc7a)
> python -c "from automisc.tools.paths import resolve_tool_binary; print(resolve_tool_binary('qemu-img'))"
D:\hacktools\misc\automisc-fresh\extend-tools\bin\win-x64\qemu\qemu-img.exe
> python -m pytest tests\unit\tools\misc\archive\test_qemu_img.py
========================= 13 passed in 0.14s ========================
```

## 4. 影响

- 0 真实二进制依赖（qemu-img 不装也能跑 auto-run，友好提示代替崩溃）
- 0 base.py 改动（架构层不动）
- 0 新基础设施（复用 resolve_tool_binary）
- 实战触发 1 道同类 (flag.vmdk) — 实战 ≥3 道同类再考虑升架构（base.py stderr 普适化）

## 5. 关联

- **实战训练**: [`v0.5-train-018-vmdk-extract.md`](./v0.5-train-018-vmdk-extract.md) — flag.vmdk 实战原文档
- **装法 spec**: [`v0.5-qemu-img-extend-tools.md`](./v0.5-qemu-img-extend-tools.md) — install.ps1 qemu_img_setup_silent
- **升架构 spec**: [`v0.5-qemu-img-adapter.md`](./v0.5-qemu-img-adapter.md) — 本 fix 在该 spec 框架内, 不增 spec
- **AGENTS §7 速查**: 修复记录 `fix_<bug>.md` 在 `upgrade/` 子目录（per 2026-06-28 治理澄清）
