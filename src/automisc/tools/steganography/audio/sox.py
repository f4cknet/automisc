"""sox adapter（per ``tools.md`` §3.6）

``sox``：音频处理瑞士军刀（转换 / 频谱 / 特效）。

**v0.1 范围**（最小可用 — Audio Stego）：
- ``soxi`` / ``sox --i``：探测元数据（与 ffmpeg_audio 互补）
- 检测异常：duration=0 / sample_rate 异常（<8kHz 或 >192kHz）
- 不做频谱图（v0.5+ 用 matplotlib 可视化频谱）

**v0.1 仅做元数据探测** —— 频谱隐写检测留给 v0.5+。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# soxi / sox --i 输出关键字段
_DURATION_RE = re.compile(r"Duration\s*:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})\s*=\s*(\d+\.?\d*)s", re.IGNORECASE)
_SAMPLE_RATE_RE = re.compile(r"Sample Rate\s*:\s*(\d+)", re.IGNORECASE)
_CHANNELS_RE = re.compile(r"Channels\s*:\s*(\d+)", re.IGNORECASE)


@register_tool
class SoxAdapter(ToolAdapter):
    """`sox` audio adapter —— 元数据探测（与 ffmpeg_audio 互补）。"""

    name = "sox"
    category = "steganography_audio"
    description = "音频元数据探测（soxi；与 ffmpeg_audio 互补）"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        # sox --i 相当于 soxi（macOS 上 soxi 可能不存在，统一用 sox --i）
        cmd = [self.binary_path or "sox", "--i", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []
        combined = stdout

        # 1. 通用扫描
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=combined,
        ))

        # 2. duration
        m = _DURATION_RE.search(combined)
        if m:
            total_sec = float(m.group(5))
            if total_sec == 0:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="audio_meta_suspicious",
                        offset=None,
                        matched_pattern="duration=0 (空音频)",
                        severity=3,
                        suggested_action="空音频文件常见于隐写",
                    )
                )
            else:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="audio_meta",
                        offset=None,
                        matched_pattern=f"duration={total_sec:.2f}s",
                        severity=1,
                        suggested_action="记录时长",
                    )
                )

        # 3. sample rate 异常
        m = _SAMPLE_RATE_RE.search(combined)
        if m:
            sr = int(m.group(1))
            if sr < 8000 or sr > 192000:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="audio_meta_suspicious",
                        offset=None,
                        matched_pattern=f"sample_rate={sr} (异常：<8kHz 或 >192kHz)",
                        severity=2,
                        suggested_action="异常 sample rate 可能为 LSB 隐写或频谱隐写信号",
                    )
                )
            else:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="audio_meta",
                        offset=None,
                        matched_pattern=f"sample_rate={sr}",
                        severity=1,
                        suggested_action="记录 sample rate",
                    )
                )

        # 4. channels
        m = _CHANNELS_RE.search(combined)
        if m:
            ch = int(m.group(1))
            if ch not in (1, 2):
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="audio_meta_suspicious",
                        offset=None,
                        matched_pattern=f"channels={ch} (异常：通常 1=mono, 2=stereo)",
                        severity=2,
                        suggested_action="多通道音频可能用于隐写",
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
