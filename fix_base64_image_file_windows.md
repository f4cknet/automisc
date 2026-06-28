# fix-base64-image-file-windows — `base64-image` decoder 在 Windows 上 file 命令找不到

> **状态**：🚧 in-progress（实施中）
> **触发**：Owner 2026-06-28 14:15 实战报错
> **关联任务行**：v0.5-base64-image（main `100189c`）
> **关联 spec**：v0.5-platform-extend-tools（`resolve_tool_binary` 设计来源）+ v0.5-windows-tool-compat（`file.exe` 部署在 extend-tools/bin/win-x64/）

---

## 1. 现象（Owner 报告 · 2026-06-28 14:15）

```
=== Decoder: base64-image (file mode) ===

=== File: C:\Users\zmzsg\Downloads\75db0674779bf8ac1f94888132932404a8baa3e997f2a41fa8aef82362d08212\KEY.exe

[!] decoder base64-image failed: Base64ImageError: 转图片失败, file 检测: (empty / no file command)
```

- 输入：真实题 KEY.exe（per `tests/unit/core/decoders/test_base64_image.py::test_real_KEY_exe`，含 `data:image/jpg;base64,...` 头 → 期望解出 133x133 RGBA PNG）
- 报错时间：KEY.exe 拖入 / 命令行触发后
- 期望：成功解出 133x133 RGBA PNG 到同目录

## 2. 根因

`src/automisc/core/decoders/base64_image.py:128`：

```python
def _file_detect(path: str) -> str:
    """`file --brief` 检测文件 mime. 失败返回空字符串."""
    file_bin = shutil.which("file")     # ← 这里在 Windows 上 None
    if not file_bin:
        return ""                       # ← 触发 Base64ImageError "empty / no file command"
    ...
```

**为什么错**：
- Windows 系统 PATH 里**没有** `file` 命令（POSIX 工具，Win 原生不带）
- v0.5-platform-extend-tools 已经把 `file.exe` v5.29 部署到 `extend-tools/bin/win-x64/file.exe`（per `extend-tools/manifest.yaml` v1.1 + 2026-06-28 PR2 install 实装）
- `_file_detect` 没用 `automisc.tools.paths.resolve_tool_binary("file")`（后者会走 PATH 优先 → extend-tools fallback）

## 3. 修复方案

### 3.1 主修（最小改动 · 1 行）

`base64_image.py` import + `_file_detect` 改用 `resolve_tool_binary`：

```python
# 顶部 import
from automisc.tools.paths import resolve_tool_binary

def _file_detect(path: str) -> str:
    """`file --brief` 检测文件 mime. 失败返回空字符串.

    平台解析 (per v0.5-platform-extend-tools):
    1) PATH 优先 (macOS /usr/bin/file, Linux /usr/bin/file)
    2) fallback extend-tools/bin/<platform>/file.exe (Windows prebuilt v5.29)
    """
    file_bin = resolve_tool_binary("file")
    if not file_bin:
        return ""
    try:
        r = subprocess.run(
            [file_bin, "--brief", path],
            ...
        )
        ...
```

### 3.2 副修（错误信息更友好）

`_file_detect` 返回空时，`decode_file_to_image` 抛错信息**仍提示 Owner 怎么修**：

```python
if not _is_image_mime(detected):
    out_path.unlink(missing_ok=True)
    # 之前: f"转图片失败, file 检测: {detected or '(empty / no file command)'}"
    if not detected:
        # file 命令找不到 — 给 Owner 明确指引
        raise Base64ImageError(
            "转图片失败: file 命令未找到。"
            "Windows 端确认 extend-tools/bin/win-x64/file.exe 存在"
            "（跑 install.ps1 装），macOS 自带无需处理。"
        )
    raise Base64ImageError(f"转图片失败, file 检测: {detected}")
```

### 3.3 不动范围

- ❌ 不改 `_try_with_fallback_headers` / `_strip_data_url` / `_try_strict_base64_decode`（base64 解析层无 bug）
- ❌ 不改 `output_path_for` 同目录策略（per v0.5-output-samedir）
- ❌ 不改 CLI / GUI 入口（已存在 + 已工作）
- ❌ 不删 `file` 命令调用（保留设计意图：让系统级 `file` 验证 mime，比自己写 magic byte 库更通用）

## 4. 验证（6 关 · per AGENTS §1 铁律 4）

| 关 | 内容 | 状态 |
|---|---|---|
| 1 | 代码合 main（待 push）| ⏳ |
| 2 | `pytest -m "not integration"` 全绿（test_base64_image.py 全部）| ⏳ |
| 3 | GUI 行为变更？**否**（只改后端 + 错误文案，GUI 渲染不变）| n/a |
| 4 | 真实样本 smoke：`automisc decode base64-image --file <KEY.exe>` Win 端跑通 | ⏳ |
| 5 | Owner 自审 | ⏳ |
| 6 | 文档同步：`fix.md` 加索引行 | ⏳ |

## 5. 测试

### 5.1 现有测试影响

- `test_real_KEY_exe`（line 186-199）：依赖 `file` 命令 → 之前 macOS CI 跑通，**Win 端修复后才会跑通**（per §4 关 4 smoke）
- 其余 7 个 case 全部不依赖 `file`（走 `_strip_data_url` / `_strip_padding` / `_try_with_fallback_headers`）→ 不受影响

### 5.2 新增测试

`test_base64_image.py` 加 3 case：

1. `test_file_detect_uses_resolve_tool_binary`：mock `resolve_tool_binary` 确认 `_file_detect` 走它（不是 `shutil.which`）
2. `test_file_detect_no_file_binary`：mock `resolve_tool_binary` 返回 None → `_file_detect` 返回空 → `decode_file_to_image` 抛新文案（"file 命令未找到"）
3. `test_decode_file_to_image_windows_no_file_binary`：mock `resolve_tool_binary` 返回 None → 抛 `Base64ImageError`，错误信息含 "extend-tools" 提示

### 5.3 Smoke 跑通标

```
$ automisc decode base64-image --file "C:\Users\zmzsg\Downloads\...\KEY.exe"
✅ 解出 PNG image data, 133 x 133, 8-bit/color RGBA, non-interlaced
   -> <input_dir>\KEY__base64.png (2884 bytes)
```

vs 修复前：

```
[!] decoder base64-image failed: Base64ImageError: 转图片失败, file 检测: (empty / no file command)
```

## 6. 决策点

无（per AGENTS §5.2 不属于"单题打补丁陷阱"）：
- ✅ `shutil.which("file")` → `resolve_tool_binary("file")` 是**项目既定模式**（per v0.5-platform-extend-tools，5 个 adapter 早这么做）
- ✅ 改 1 行 + 加 3 单测，影响面小
- ✅ Win 端 file.exe 缺失会导致 base64-image 全 fail（per `v0.5-windows-tool-compat` PR2 实装，file.exe 已就位）

直接修，无须 Owner 拍板。

## 7. 提交策略

per AGENTS §2.4 单 Owner 简化 + v2.4 "完全信任 AI"：

1. 本地 commit（不 push）
2. 询问卡等 Owner Y 后 push

commit message：

```
fix(base64-image): 修复 Windows 端 file 命令找不到导致 base64-image decoder 全部失败

src/automisc/core/decoders/base64_image.py:_file_detect 用 shutil.which("file")
在 Windows 上 None（POSIX 工具 Win 原生不带），导致所有 base64-image 解码
失败（报 "file 检测: (empty / no file command)"）。

修复: 改用 automisc.tools.paths.resolve_tool_binary("file") — 自动
PATH 优先 → extend-tools/bin/win-x64/file.exe fallback（v5.29 prebuilt
已就位 per v0.5-windows-tool-compat PR2）。

副修: 错误文案增加 "file 命令未找到" 提示 + extend-tools 排错指引。

测试: +3 单测（resolve_tool_binary 调用 + 无 file 兜底 + 错误文案）

关联: fix-base64-image-file-windows spec
```

## 8. 关联 spec

- v0.5-base64-image（`100189c`）— base64-image decoder 原始 spec
- v0.5-platform-extend-tools（`resolve_tool_binary` 来源）
- v0.5-windows-tool-compat（file.exe v5.29 prebuilt 部署，PR2 已实装）
