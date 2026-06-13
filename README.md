# AutoMisc

> CTF Misc 半自动化辅助工具箱（macOS GUI / 完全离线 / PySide6）

详细开发文档：
- [`AGENTS.md`](./AGENTS.md) — 治理宪法（4 条铁律）
- [`prd.md`](./prd.md) — 需求 + 任务看板
- [`Architecture.md`](./Architecture.md) — 系统架构
- [`tools.md`](./tools.md) — 外部工具清单

## 状态

**v0.1.0b-PR1** ✅ 已完成（共享基础工具 6 个 adapter + Core 调度层 + 61 unit tests）

后续 PR（per `tools.md §6.2`）：
- v0.1.0b-PR2：Stego/Image（zsteg / steghide）
- v0.1.0b-PR3：Forensics/Network（tshark / tcpdump）
- v0.1.0b-PR4：Stego/Audio+Video（ffmpeg / ffprobe + sox 安装）
- v0.1.0b-PR5：Misc/Archive（7z / unzip + john 安装）
- v0.1.0b-PR6：Forensics/Log（grep + evtx_dump + python-evtx 安装）
- v0.1.0b-PR7：Forensics/Memory（vol.py 恢复）
- v0.1.0b-PR8：Misc/Brainteaser QR（zbar 安装）
- v0.1.0b-PR9：Python 包基座（python-magic-bin + numpy 安装）
- v0.1.1：GUI（PySide6）

## 安装

```bash
# 用 pyenv 的 Python（避开 Homebrew PEP 668）
PYTHON_PATH=/Users/minzhizhou/.pyenv/shims/python
$PYTHON_PATH -m pip install -e .

# 安装 dev 依赖
$PYTHON_PATH -m pip install pytest pytest-mock
```

## CLI 用法

```bash
PYTHONPATH=src python3 -m automisc tools list     # 列出已注册工具
PYTHONPATH=src python3 -m automisc run --tool strings --file /path/to/file
```

## 测试

```bash
pytest tests/unit -q    # 61 tests / 100% PASS
```
