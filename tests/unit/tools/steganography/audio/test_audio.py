"""测试 tools/steganography/audio/"""
from __future__ import annotations

import pytest

from automisc.core.registry import get_tool
from automisc.tools.steganography.audio.ffmpeg_audio import FfmpegAudioAdapter
from automisc.tools.steganography.audio.sox import SoxAdapter
from automisc.tools.steganography.audio.steghide_audio import SteghideAudioAdapter


WAV_FIXTURE = "tests/fixtures/sample_audio_flag.wav"


def test_ffmpeg_audio_adapter_is_registered():
    a = get_tool("ffmpeg_audio")
    assert isinstance(a, FfmpegAudioAdapter)


def test_ffmpeg_audio_adapter_extracts_meta(wav_fixture):
    a = FfmpegAudioAdapter()
    result = a.run(wav_fixture)
    assert result.is_success
    meta_sp = [sp for sp in result.suspicious_points if sp.category == "audio_meta"]
    assert any("duration=" in sp.matched_pattern for sp in meta_sp)


def test_ffmpeg_audio_adapter_extracts_flag(wav_fixture):
    """fixture 含 flag metadata → 应该命中。"""
    a = FfmpegAudioAdapter()
    result = a.run(wav_fixture)
    flag_sp = [sp for sp in result.suspicious_points if sp.category == "flag"]
    assert any("flag{pr4_smoke_audio_wav_xyz}" in sp.matched_pattern for sp in flag_sp)


def test_ffmpeg_audio_adapter_handles_missing_file(tmp_path):
    a = FfmpegAudioAdapter()
    result = a.run(str(tmp_path / "ghost.wav"))
    assert result.exit_code != 0


def test_sox_adapter_is_registered():
    a = get_tool("sox")
    assert isinstance(a, SoxAdapter)


def test_sox_adapter_extracts_sample_rate(wav_fixture):
    a = SoxAdapter()
    result = a.run(wav_fixture)
    sr_sp = [sp for sp in result.suspicious_points if "sample_rate" in sp.matched_pattern]
    assert any("44100" in sp.matched_pattern for sp in sr_sp)


def test_sox_adapter_handles_missing_file(tmp_path):
    a = SoxAdapter()
    result = a.run(str(tmp_path / "ghost.wav"))
    assert result.exit_code != 0


def test_steghide_audio_adapter_is_registered():
    a = get_tool("steghide_audio")
    assert isinstance(a, SteghideAudioAdapter)


def test_steghide_audio_adapter_handles_no_tty(wav_fixture):
    """subprocess 无 tty → steghide unavailable 信号（不 panic）。"""
    a = SteghideAudioAdapter()
    result = a.run(wav_fixture)
    # exit_code 非 0（steghide 需要 tty）
    # 但 should 有 capacity / unavailable suspicious point
    assert any(sp.category == "steghide_capacity" or sp.category == "steghide_unavailable"
               for sp in result.suspicious_points)


# === fixtures ===

@pytest.fixture
def wav_fixture():
    import os
    if not os.path.exists(WAV_FIXTURE):
        pytest.skip(f"fixture not found: {WAV_FIXTURE}")
    return WAV_FIXTURE
