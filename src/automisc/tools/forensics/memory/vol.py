"""vol.py adapter（per ``tools.md`` §3.1）

``vol3``（volatility3）：官方 Python 3 实现的内存取证框架。

**v0.1 范围**（最小可用 — Memory Forensics）：
- 调用 ``vol3 -f <vmem> windows.pslist`` / ``windows.netscan`` / ``windows.filescan`` / ``windows.clipboard``
  等插件
- **仅做 CLI 包装**：subprocess 调 vol3，解析输出（tab 格式文本）
- 命中 flag / 关键字（per tools.md §3.1）→ severity 5/3
- vol3 自动 profile 检测（用户不需要指定）

**v0.1 不做**：
- 真实 .vmem 镜像 fixture（太大；v0.5+ 准备小型 test vmem）
- 插件输出 deep parse（用通用 flag 扫描即可）
- vol2 docker wrapper（per PR7-envfix 决策留 v0.5+）

**macOS**：vol3 装好（per PR7-envfix `pip install volatility3`）。
"""
from __future__ import annotations

import json
import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# v0.1 跑的 vol3 插件（per tools.md §3.1）
# 顺序按 CTF 使用频率排
_VOL3_PLUGINS = [
    ("windows.pslist", "进程列表（找可疑进程）"),
    ("windows.pstree", "进程树（父子关系）"),
    ("windows.netscan", "网络连接（找 C2 / 后门端口）"),
    ("windows.filescan", "文件扫描（找敏感文件名）"),
    ("windows.cmdline", "进程命令行（找恶意命令）"),
    ("windows.clipboard", "剪贴板（可能有 flag）"),
    ("windows.registry.hivelist", "注册表 hive（高级分析）"),
    ("windows.registry.printkey", "注册表键值（找 run/malware 启动项）"),
]


# v0.1 跑前 4 个就够（pslist + pstree + netscan + filescan），减少 fixture 大小
_DEFAULT_PLUGINS = ["windows.pslist", "windows.pstree", "windows.netscan", "windows.filescan"]


@register_tool
class VolAdapter(ToolAdapter):
    """`vol3` adapter —— 内存镜像分析（volatility3，per PR7-envfix 决策）。"""

    name = "vol"
    category = "forensics_memory"
    description = "Volatility 3 内存取证（windows.pslist/pstree/netscan/filescan/cmdline/clipboard 等）"

    default_timeout = 120.0  # vol3 跑大 vmem 慢

    def run(self, file_path: str) -> ToolResult:
        # v0.1 策略：直接用当前 Python 调 volatility3.cli main
        # 通过 -c 把 argv 注入 sys.argv
        # （不依赖外部 vol binary，pyenv shim 复杂且可能用错 Python 版本）
        all_stdout: list[str] = []
        all_stderr: list[str] = []
        last_exit = 0
        total_duration = 0

        for plugin in _DEFAULT_PLUGINS:
            # 把 argv 传给 main() 避免 argparse 把 -c 当 flag
            cmd = [
                "python3", "-c",
                f"import sys; sys.argv = ['vol', '-f', '{file_path}', '{plugin}']; "
                f"from volatility3.cli import main; main()",
            ]
            try:
                exit_code, stdout, stderr, duration_ms = self._run_subprocess(
                    cmd, timeout=60
                )
            except Exception as e:  # noqa: BLE001
                all_stderr.append(f"[{plugin}] adapter error: {e}")
                continue

            all_stdout.append(f"=== {plugin} ===\n{stdout}")
            all_stderr.append(f"[{plugin}] {stderr}")
            last_exit = exit_code
            total_duration += duration_ms

            # 任一 plugin 成功（exit 0）就 break 后续 → v0.1 节省时间
            if exit_code == 0:
                break

        combined_stdout = "\n".join(all_stdout)
        combined_stderr = "\n".join(all_stderr)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描（flag / base64 / keyword）
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=combined_stdout,
        ))

        # 2. 检测 vol3 报错 → unavailable 信号
        if "Volatility 3 Framework" not in combined_stdout and "Stacking attempts" not in combined_stdout:
            if "cannot" in combined_stderr.lower() or "error" in combined_stderr.lower():
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="vol3_unavailable",
                        offset=None,
                        matched_pattern=f"vol3 调用失败：{combined_stderr[:200]!r}",
                        severity=1,
                        suggested_action=(
                            "检查 vol3 是否装好 (pip install volatility3)；"
                            "或文件不是有效 vmem 镜像"
                        ),
                    )
                )

        # 3. 记录跑的插件（meta）
        for plugin in _DEFAULT_PLUGINS:
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="vol3_plugin",
                    offset=None,
                    matched_pattern=f"vol3 plugin {plugin} ({_VOL3_PLUGINS[[p[0] for p in _VOL3_PLUGINS].index(plugin)][1]})",
                    severity=1,
                    suggested_action="记录运行的 vol3 插件",
                )
            )

        return ToolResult(
            tool_name=self.name,
            exit_code=last_exit,
            stdout=combined_stdout,
            stderr=combined_stderr,
            suspicious_points=suspicious,
            duration_ms=total_duration,
        )
