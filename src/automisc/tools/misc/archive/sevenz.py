"""7z adapter（per ``tools.md`` §3.9）

``7z``：7-Zip CLI，**最强通用解压工具**（支持 zip / 7z / rar / tar / gz / bz2 / xz / iso 等 30+ 格式）。

**v0.1 范围**（最小可用 — Archive Stego）：
- ``7z l <file>`` —— list archive contents（不解压）
- 解析 list 输出，提取：file count / total size / compression ratio
- 伪加密检测：7z 报 "Wrong password" 或 "Headers Error" → 强信号 [4]
- 不做实际解压（GUI 触发解压到指定目录）

**macOS**：`brew install p7zip`（已装）。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# 7z l 输出关键行
_FILE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+[.\-A-Za-z]+\s+\d+\s+\d+\s+(.+)$")

# 强信号：伪加密 / 损坏 / 错密码
_PSEUDO_ENCRYPTION_HINTS = [
    "Wrong password",
    "Headers Error",  # 伪加密时 ZIP 头标记 + 数据不匹配
    "cannot open the file as archive",
    "Data Error",  # 损坏 / 密码错
    "Encrypted = +",
]


@register_tool
class SevenZipAdapter(ToolAdapter):
    """`7z` adapter —— 通用归档探测（list / 伪加密检测）。"""

    name = "sevenz"
    category = "misc_archive"
    description = "7-Zip CLI — 通用归档 list + 伪加密检测（zip/7z/rar/tar/gz/bz2 等 30+ 格式）"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        # 7z t: test mode（不解压但 CRC 校验 + 密码尝试）
        # 用空密码 -p""：如果文件标记加密且密码非空，会报 "Wrong password"（伪加密信号）
        # 如果是真加密 + 正确密码，list 阶段就够
        # 策略：先 list 看文件结构（拿到 file count），再 test 探伪加密
        cmd_list = [self.binary_path or "7z", "l", file_path]
        ec_l, stdout_l, stderr_l, dur_l = self._run_subprocess(cmd_list)

        cmd_test = [self.binary_path or "7z", "t", "-p", file_path]
        ec_t, stdout_t, stderr_t, dur_t = self._run_subprocess(cmd_test)

        # 合并两次输出做检测
        exit_code = ec_t  # test 退出码更能反映问题
        stdout = stdout_l + "\n" + stdout_t
        stderr = stderr_l + "\n" + stderr_t
        duration_ms = dur_l + dur_t

        suspicious: list[SuspiciousPoint] = []
        combined = (stdout + "\n" + stderr).lower()

        # 1. 通用扫描
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 伪加密 / 损坏信号
        for hint in _PSEUDO_ENCRYPTION_HINTS:
            if hint.lower() in combined:
                severity = 4 if ("wrong password" in combined or "headers error" in combined) else 3
                action = (
                    "ZIP/7z 伪加密信号：建议 foremost 提取 + john 爆破 + "
                    "或尝试 16 进制改 flag 位 (0x09 → 0x00)"
                    if "headers error" in combined else
                    "归档含密码 / 损坏：建议 GUI 触发解压到指定目录（带密码）或用 john"
                )
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="archive_pseudo_encryption",
                        offset=None,
                        matched_pattern=f"7z: {hint}",
                        severity=severity,
                        suggested_action=action,
                    )
                )
                break  # 只报第一个

        # 3. 文件计数（从 list 输出解析）
        file_count = 0
        total_size = 0
        for line in stdout.splitlines():
            # 7z l 输出每行: "2026-06-13 12:34:56 ....A         1234   file/path"
            # 更简单的方式：数包含日期的行
            if re.match(r"^\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", line):
                file_count += 1

        if file_count > 0:
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="archive_meta",
                    offset=None,
                    matched_pattern=f"archive contains {file_count} files",
                    severity=1,
                    suggested_action="记录归档内容数量便于交叉验证",
                )
            )

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )
