# fix-resolve-tool-binary-subdir — `resolve_tool_binary` 加 subdir fallback 找 steghide

> **状态**：🚧 in-progress（实施中）  
> **触发**：Owner 2026-06-28 16:30 实战报错  
> **关联任务行**：v0.5-stegseek-remove (per `f70aeb4` 后 steghide adapter 仍 FAIL)  
> **关联 spec**：v0.5-windows-tool-compat（steghide Cygwin build 部署, subdir 布局根因）

---

## 1. 现象（Owner 报告 · 2026-06-28 16:30）

```
=== steghide (auto FAIL) ===
[stderr] steghide 二进制未找到 (PATH 缺失或 extend-tools 未装)
exit_code: 127 | suspicious_points (1): [1] steghide_unavailable: steghide 二进制未找到 ...
```

- 输入：拖入 JPEG / BMP (任何 steghide 候选文件)
- v0.5-stegseek-remove 7 commit 推完后: steghide adapter **永远 FAIL** (exit 127)
- 即使 extend-tools/bin/win-x64/steghide/steghide.exe 实际就位
- 原因: `resolve_tool_binary("steghide")` 走 flat 路径 `bin/win-x64/steghide.exe`, 不存在, 返回 None

## 2. 根因

`src/automisc/tools/paths.py:resolve_tool_binary`（v0.5-platform-extend-tools 治理）:

```python
def resolve_tool_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    bindir = extend_tools_bin_dir()
    if bindir is None:
        return None
    candidate = bindir / f"{name}{exe_suffix()}"   # ← 只看 flat
    if candidate.exists():
        return str(candidate)
    return None
```

只检查 flat 布局 `bin/<win-x64>/<name>.exe`，**不**看 subdir 布局 `bin/<win-x64>/<name>/<name>.exe`。

## 3. 为什么 steghide 是 subdir 布局

`extend-tools/manifest.yaml` v1.1 steghide entry 注释:
```
steghide:
  version: "0.5.1-cygwin"
  notes: |
    steghide (JPEG/BMP/WAV/AU 隐写 + 口令) Cygwin build v0.5.1.
    部署到 extend-tools/bin/win-x64/steghide/ 子目录:
      - steghide.exe
      - cygwin1.dll (Cygwin runtime, 必带)
      - cygiconv-2.dll / cygintl-2.dll / cygjpeg-62.dll / cygmcrypt-4.dll / cygmhash-2.dll / cygz.dll
      - locale/{de,es,fr,ro}/LC_MESSAGES/steghide.mo
```

subdir 原因: Cygwin runtime 依赖 (cygwin1.dll + 7 个 cyg*.dll) 必须跟 steghide.exe **同目录**, 否则 Windows DLL search 失败. 移到 flat 布局会破坏运行.

## 4. 修复方案

### 4.1 主修（1 文件, ~5 LOC）

`src/automisc/tools/paths.py:resolve_tool_binary` 加 subdir fallback:

```python
def resolve_tool_binary(name: str) -> str | None:
    """..."""
    found = shutil.which(name)
    if found:
        return found
    bindir = extend_tools_bin_dir()
    if bindir is None:
        return None
    # 1) flat layout: <bin>/<name>.exe (file / exiftool / foremost / 7z / ...)
    candidate = bindir / f"{name}{exe_suffix()}"
    if candidate.exists():
        return str(candidate)
    # 2) subdir layout: <bin>/<name>/<name>.exe (steghide Cygwin build, per v0.5-windows-tool-compat)
    #    原因: Cygwin runtime DLLs 必须跟 .exe 同目录, 不能 flat
    sub_candidate = bindir / name / f"{name}{exe_suffix()}"
    if sub_candidate.exists():
        return str(sub_candidate)
    return None
```

### 4.2 不动范围

- ❌ 不动 steghide manifest (subdir 布局是 Cygwin 依赖必要, 不可 flat)
- ❌ 不动 `SteghideAdapter` / `SteghideCrackAction` / `SteghideExtractAction` (已经走 `resolve_tool_binary`, 修 paths.py 自动生效)
- ❌ 不动其他工具 adapter (file/exiftool/7zr/foremost 都是 flat 布局, 不受影响)
- ❌ 不动 `extend-tools/install.ps1` (manifest 跟 install.ps1 部署路径一致, 无需改)

### 4.3 副作用 / 风险

| 风险 | 概率 | 缓解 |
|---|---|---|
| **subdir fallback 误命中其他工具** | 🟢 低 | 工具名 = 子目录名 (steghide/steghide.exe) 极罕见; flat 不存在才会查 subdir, 不冲突 |
| **steghide 仍跑失败** (Cygwin DLL 缺失) | 🟢 低 | 已经在 extend-tools/bin/win-x64/steghide/ 部署完整, smoke 验证 |
| **跨平台影响** | 🟢 无 | 改动只影响 Win 端 extend-tools fallback; macOS/Linux 走 PATH, 不变 |

## 5. 验证（6 关 · per AGENTS §1 铁律 4）

| 关 | 内容 | 状态 |
|---|---|---|
| 1 | 代码合 main | ⏳ local commit（待 push）|
| 2 | pytest 单测全绿 | ⏳ |
| 3 | GUI 行为变更？**否**（仅改路径解析）| n/a |
| 4 | 真实样本 smoke：`steghide info <file>` 跑通 + steghide extract -p "" 命中 | ⏳ |
| 5 | Owner 自审 | ⏳ |
| 6 | 文档同步: fix.md 索引 + STRUCTURE.md (extend-tools 章节, 如有) | ⏳ |

### 5.1 关键 smoke

```powershell
PS> python -c "from automisc.tools.paths import resolve_tool_binary; print(resolve_tool_binary('steghide'))"
D:\hacktools\misc\automisc-fresh\extend-tools\bin\win-x64\steghide\steghide.exe   ← 修复后

PS> python -m automisc decode base64-image --file tests/fixtures/smoke/KEY_fixture.exe
# 不相关, 用 steghide 真实题:

PS> .\extend-tools\bin\win-x64\steghide\steghide.exe info <某 steghide 真实题>
# 修复后应输出 capacity + 命中
```

## 6. 决策点

无（per AGENTS §5.2 不属于"单题打补丁陷阱"）:
- 改动小（5 LOC）, 范围明确
- subdir 布局根因 Cygwin 依赖, **必须** 这样部署（不能 flat 化）
- 所有 v0.5+ 实战命中此问题（Owner 实战 + 我 PR1 单测全 skip 原因同根因）
- 修复后 SteghideAdapter / SteghideCrackAction / SteghideExtractAction 全部能跑, +15+ 单测从 skip → pass

## 7. 提交策略

per AGENTS §2.4 单 Owner 简化 + "完全信任 AI":

1. 1 local commit (paths.py + tests)
2. 询问卡等 Owner Y 后 push（**跟 v0.5-stegseek-remove 7 commit 一起推**, 8 commit 1 PR）

commit message:

```
fix(paths): resolve_tool_binary 加 subdir fallback 找 steghide Cygwin build

steghide 实装在 extend-tools/bin/win-x64/steghide/steghide.exe (subdir,
Cygwin DLL 依赖同目录), 但 resolve_tool_binary 只看 flat bin/<win-x64>/<name>.exe,
导致 v0.5-stegseek-remove 7 commit 推完后 SteghideAdapter 等永远 FAIL (exit 127).

修复: resolve_tool_binary 加 subdir fallback, 检查
<bin>/<name>/<name>.exe (per v0.5-windows-tool-compat steghide 部署).

影响:
- SteghideAdapter (auto_run) + SteghideCrackAction (字典爆破) +
  SteghideExtractAction (指定密码提取) 全部能跑
- v0.5-stegseek-remove PR1 15+ 单测从 skip 转 pass (Win 端 steghide 缺失)
- 误命中风险低 (subdir 布局仅 steghide 用, 工具名 = 子目录名 极罕见)

关联: v0.5-stegseek-remove + v0.5-windows-tool-compat + v0.5-base64-image
```

## 8. 关联 spec

- v0.5-stegseek-remove（依赖本修复才能让 SteghideAdapter 跑起来）
- v0.5-windows-tool-compat（steghide Cygwin build 部署, subdir 布局根因）
- v0.5-platform-extend-tools（`resolve_tool_binary` 设计, 当前 flat-only 缺陷）
- v0.5-base64-image（file 命令走 extend-tools flat 布局, 跟本修复并列 — Win 端)
