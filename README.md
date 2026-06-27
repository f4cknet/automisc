# AutoMisc

> CTF Misc 半自动化辅助工具箱（Windows GUI / 完全离线 / PySide6）

详细开发文档：
- [`AGENTS.md`](./AGENTS.md) — 治理宪法（7 条铁律）
- [`prd.md`](./prd.md) — 需求 + 任务看板
- [`STRUCTURE.md`](./STRUCTURE.md) — 系统架构
- [`tools.md`](./tools.md) — 外部工具清单

## 状态

**v0.5+** ✅ 已迭代 60+ 次（共享基础工具 + Core 调度层 + GUI + DAG chain + 1027 unit tests）

**平台**：**Windows only**（per `AGENTS.md §2.3 v3.3` 治理变更 2026-06-27）。工具链走 `extend-tools/bin/win-x64/`（binwalk.exe / exiftool.exe / 7zr.exe / foremost.exe 等）。

## 安装

```powershell
# Windows: 用 pyenv 的 Python（避开 PEP 668）
$PY = "C:\Users\$env:USERNAME\.pyenv\pyenv-win\versions\3.13.6\python.exe"
& $PY -m pip install -e .

# 安装外部工具（4 个核心：binwalk / exiftool / 7z / foremost）
.\extend-tools\install.ps1

# 安装 dev 依赖
& $PY -m pip install pytest pytest-mock
```

## CLI 用法

```powershell
# 列出已注册工具
python -m automisc tools list

# 跑工具
python -m automisc run --tool strings --file C:\path\to\file

# 启动 GUI
automisc-gui
```

## 测试

```powershell
pytest tests/unit -q    # 1027 tests / PASS
```
