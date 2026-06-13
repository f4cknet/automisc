"""测试 tools/steganography/video/"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool
from automisc.tools.steganography.video.ffmpeg_video import FfmpegVideoAdapter
from automisc.tools.steganography.video.ffprobe import FfprobeAdapter


MP4_FIXTURE = "tests/fixtures/sample_video_flag.mp4"


def test_ffprobe_adapter_is_registered():
    a = get_tool("ffprobe")
    assert isinstance(a, FfprobeAdapter)


def test_ffprobe_adapter_extracts_flag(mp4_fixture):
    a = FfprobeAdapter()
    result = a.run(mp4_fixture)
    assert result.is_success
    flag_sp = [sp for sp in result.suspicious_points if sp.category == "flag"]
    assert any("flag{pr4_smoke_video_mp4_abc}" in sp.matched_pattern for sp in flag_sp)


def test_ffprobe_adapter_extracts_streams(mp4_fixture):
    a = FfprobeAdapter()
    result = a.run(mp4_fixture)
    stream_sp = [sp for sp in result.suspicious_points if sp.category == "video_meta"]
    assert any("nb_streams=2" in sp.matched_pattern for sp in stream_sp)


def test_ffprobe_adapter_handles_missing_file(tmp_path):
    a = FfprobeAdapter()
    result = a.run(str(tmp_path / "ghost.mp4"))
    assert result.exit_code != 0


def test_ffmpeg_video_adapter_is_registered():
    a = get_tool("ffmpeg_video")
    assert isinstance(a, FfmpegVideoAdapter)


def test_ffmpeg_video_adapter_extracts_meta(mp4_fixture):
    a = FfmpegVideoAdapter()
    result = a.run(mp4_fixture)
    assert result.is_success
    duration_sp = [sp for sp in result.suspicious_points if sp.category == "video_meta" and "duration" in sp.matched_pattern]
    assert any("duration=" in sp.matched_pattern for sp in duration_sp)


def test_ffmpeg_video_adapter_extracts_flag(mp4_fixture):
    a = FfmpegVideoAdapter()
    result = a.run(mp4_fixture)
    flag_sp = [sp for sp in result.suspicious_points if sp.category == "flag"]
    assert any("flag{pr4_smoke_video_mp4_abc}" in sp.matched_pattern for sp in flag_sp)


def test_ffmpeg_video_adapter_handles_missing_file(tmp_path):
    a = FfmpegVideoAdapter()
    result = a.run(str(tmp_path / "ghost.mp4"))
    assert result.exit_code != 0


# === fixtures ===

@pytest.fixture
def mp4_fixture():
    import os
    if not os.path.exists(MP4_FIXTURE):
        pytest.skip(f"fixture not found: {MP4_FIXTURE}")
    return MP4_FIXTURE
