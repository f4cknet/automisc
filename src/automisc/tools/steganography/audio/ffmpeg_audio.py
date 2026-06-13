"""ffmpeg audio adapter（per ``tools.md`` §3.6）

``ffmpeg``：多媒体转码 + 处理。

**v0.1 范围**（最小可用 — Audio Stego）：
- 探测音频文件元数据（duration / bit_rate / channels / codec）
- ``-i <file>`` 自动打印 stream 信息
- 检测可疑音频参数（如 duration=0 / 不常见 codec）

**已知音频隐写场景**：
- LSB 隐写（wav）：可结合 zsteg 思路扩展，v0.5+ 加
- 频谱隐写（mp3/wav）：v0.5+ 加 sox 频谱图
- 摩斯码 / DTMF：v0.5+ multimon-ng

**v0.1 仅做元数据探测**。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# ffmpeg -i 输出关键行（per stream）
_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
_STREAM_RE = re.compile(r"Stream\s+#\d+:\d+.*?:\s*Audio:\s*(\w+).*?(\d+)\s*Hz,\s*(\w+?)(?:,\s*(\w+))?", re.IGNORECASE)


@register_tool
class FfmpegAudioAdapter(ToolAdapter):
    """`ffmpeg` audio adapter —— 音频元数据探测。"""

    name = "ffmpeg_audio"
    category = "steganography_audio"
    description = "音频元数据探测（duration / codec / sample_rate / channels）"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        # ffmpeg -i: 仅打印 stream 信息（不实际解码）
        # -hide_banner: 隐藏 ffmpeg 编译信息 banner
        # -f null -: 不输出到文件
        cmd = [
            self.binary_path or "ffmpeg",
            "-hide_banner",
            "-i", file_path,
            "-f", "null", "-",
        ]
        # ffmpeg 在解析错误时 exit 非 0，但 stream 信息已打到 stderr
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用 flag / 关键字 / base64 扫描（基于 stderr stream 信息）
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stderr,
        ))

        # 2. duration 提取
        combined = stderr
        m = _DURATION_RE.search(combined)
        if m:
            hh, mm, ss, cs = m.groups()
            total_sec = int(hh) * 3600 + int(mm) * 60 + int(ss) + int(cs) / 100
            if total_sec == 0:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="audio_meta_suspicious",
                        offset=None,
                        matched_pattern="duration=0 (空音频文件)",
                        severity=3,
                        suggested_action="空音频文件常见于隐写（嵌入零字节头 + 实际数据在其他流）",
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
                        suggested_action="记录时长便于交叉验证",
                    )
                )

        # 3. stream codec 提取
        for m in _STREAM_RE.finditer(combined):
            codec, sample_rate, channels, *_ = m.groups()
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="audio_stream",
                    offset=None,
                    matched_pattern=f"Audio codec={codec} sample_rate={sample_rate} channels={channels}",
                    severity=1,
                    suggested_action="记录 stream 参数",
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
