"""ffmpeg video adapter（per ``tools.md`` §3.7）

``ffmpeg`` video 模式：与 audio adapter 共享 binary，仅 name/category 区别。

**v0.1 范围**（最小可用 — Video Stego）：
- ``-i <file>`` 探测元数据
- 检测非 video/audio stream（data stream 隐写强信号）
- 不做帧提取（v0.5+ 用 ffmpeg 抽帧 + zsteg 思路分析）

**v0.1 仅做元数据探测**。
"""
from __future__ import annotations

import re

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# ffmpeg -i 输出匹配 video stream
_VIDEO_STREAM_RE = re.compile(
    r"Stream\s+#\d+:\d+.*?:\s*Video:\s*(\w+)(?:\s*\([^)]*\))?.*?(\d+)x(\d+)(?:.*?(\d+(?:\.\d+)?)\s*fps)?",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})")


@register_tool
class FfmpegVideoAdapter(ToolAdapter):
    """`ffmpeg` video adapter —— 视频元数据探测（与 ffmpeg_audio 共享 binary）。"""

    name = "ffmpeg_video"
    category = "steganography_video"
    description = "视频元数据探测（codec / resolution / fps）；与 ffmpeg_audio 互补"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        cmd = [
            self.binary_path or "ffmpeg",
            "-hide_banner",
            "-i", file_path,
            "-f", "null", "-",
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stderr,
        ))

        # 2. duration
        m = _DURATION_RE.search(stderr)
        if m:
            hh, mm, ss, cs = m.groups()
            total_sec = int(hh) * 3600 + int(mm) * 60 + int(ss) + int(cs) / 100
            if total_sec == 0:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="video_meta_suspicious",
                        offset=None,
                        matched_pattern="duration=0 (空视频)",
                        severity=3,
                        suggested_action="空视频文件可能为隐写容器",
                    )
                )
            else:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="video_meta",
                        offset=None,
                        matched_pattern=f"duration={total_sec:.2f}s",
                        severity=1,
                        suggested_action="记录时长",
                    )
                )

        # 3. video stream 提取
        for m in _VIDEO_STREAM_RE.finditer(stderr):
            codec, w, h, fps = m.groups()
            fps = fps or "?"
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="video_stream",
                    offset=None,
                    matched_pattern=f"Video codec={codec} {w}x{h} fps={fps}",
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
