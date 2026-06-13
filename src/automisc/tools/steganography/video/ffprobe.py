"""ffprobe adapter（per ``tools.md`` §3.7）

``ffprobe``：多媒体流信息探测器（ffmpeg 自带）。

**v0.1 范围**（最小可用 — Video Stego）：
- ``-v error -show_format -show_streams -of json``：JSON 输出 stream 列表
- 解析：duration / bit_rate / nb_streams / codec_name / codec_type
- 检测多 stream（>2 streams 含 video+audio 之外的 stream = 可疑）

**v0.1 不做**：
- 帧级隐写（v0.5+ 用 ffmpeg 抽帧 + binwalk 分析）
- 元数据 EXIF 隐写（v0.5+ 用 exiftool 共享 adapter）
"""
from __future__ import annotations

import json

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


@register_tool
class FfprobeAdapter(ToolAdapter):
    """`ffprobe` adapter —— 视频流元数据探测。"""

    name = "ffprobe"
    category = "steganography_video"
    description = "视频流元数据探测（duration / streams / codec）；JSON 输出"

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        cmd = [
            self.binary_path or "ffprobe",
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            file_path,
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 解析 JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return ToolResult(
                tool_name=self.name,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                suspicious_points=suspicious,
                duration_ms=duration_ms,
            )

        streams = data.get("streams", [])
        fmt = data.get("format", {})

        # 3. 视频文件 stream 数检测
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
        other_streams = [s for s in streams if s.get("codec_type") not in ("video", "audio", "subtitle")]

        nb_streams = len(streams)
        if other_streams:
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="video_stream_suspicious",
                    offset=None,
                    matched_pattern=f"{len(other_streams)} 非标准 stream (类型: {[s.get('codec_type') for s in other_streams]})",
                    severity=4,
                    suggested_action="非 video/audio/subtitle stream 常用于隐写（data stream 嵌入 payload）",
                )
            )

        # 记录 stream 总览
        if nb_streams > 0:
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="video_meta",
                    offset=None,
                    matched_pattern=f"nb_streams={nb_streams} (video={len(video_streams)} audio={len(audio_streams)} subtitle={len(subtitle_streams)})",
                    severity=1,
                    suggested_action="记录 stream 数量便于交叉验证",
                )
            )

        # 4. duration
        duration = fmt.get("duration")
        if duration:
            try:
                d = float(duration)
                if d == 0:
                    suspicious.append(
                        SuspiciousPoint(
                            id="",
                            tool_name=self.name,
                            file_path=file_path,
                            category="video_meta_suspicious",
                            offset=None,
                            matched_pattern="duration=0 (空视频)",
                            severity=3,
                            suggested_action="空视频文件常见于隐写（容器有 metadata 但无实际帧）",
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
                            matched_pattern=f"duration={d:.2f}s",
                            severity=1,
                            suggested_action="记录时长",
                        )
                    )
            except ValueError:
                pass

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )
