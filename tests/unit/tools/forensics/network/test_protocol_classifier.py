"""测试 tools/forensics/network/protocol_classifier.py"""
from __future__ import annotations

import pytest

from automisc.tools.forensics.network.protocol_classifier import (
    CIPHER_PROTOCOLS,
    LINK_LAYER_PROTOCOLS,
    PLAINTEXT_AUX_PROTOCOLS,
    classify_protocols,
    parse_io_phs,
)


# ---------- 真实 pcap io,phs 输出 (greatescape.pcap) ----------
SAMPLE_IO_PHS = """\
===================================================================
Protocol Hierarchy Statistics
Filter: 

frame                                    frames:2756 bytes:935469
  sll                                    frames:2756 bytes:935469
    ip                                   frames:2756 bytes:935469
      tcp                                frames:2756 bytes:935469
        http                             frames:46 bytes:30901
          data-text-lines                frames:2 bytes:1618
          ocsp                           frames:42 bytes:27949
        tls                              frames:913 bytes:621804
          tls                            frames:97 bytes:120791
        ftp                              frames:16 bytes:1828
        ftp-data                         frames:1 bytes:3341
          data-text-lines                frames:1 bytes:3341
        smtp                             frames:33 bytes:6375
          imf                            frames:3 bytes:2976
===================================================================
"""


def test_parse_io_phs_returns_protocol_list():
    """parse_io_phs 解析 greatescape 输出得到 14 行（含 2 个嵌套 tls + 嵌套 imf 等）"""
    result = parse_io_phs(SAMPLE_IO_PHS)
    # 实际包含: frame / sll / ip / tcp / http / data-text-lines / ocsp / tls (外) / tls (内) / ftp / ftp-data / data-text-lines (内) / smtp / imf
    assert len(result) == 14
    proto_names = [r[0] for r in result]
    assert proto_names[0] == "frame"
    assert proto_names.count("tls") == 2  # 嵌套
    assert "ftp-data" in proto_names
    assert proto_names.count("data-text-lines") == 2  # http + ftp-data 各 1


def test_parse_io_phs_extracts_frames_and_bytes():
    """每行 (proto, frames, bytes) 数值正确."""
    result = parse_io_phs(SAMPLE_IO_PHS)
    # 找 tls 行
    tls_row = [r for r in result if r[0] == "tls"][0]
    assert tls_row == ("tls", 913, 621804)
    ftp_data_row = [r for r in result if r[0] == "ftp-data"][0]
    assert ftp_data_row == ("ftp-data", 1, 3341)


def test_parse_io_phs_empty_input():
    """空输入返回空列表."""
    assert parse_io_phs("") == []


def test_parse_io_phs_handles_garbage_lines():
    """非协议行（空行 / ===装饰）安全跳过."""
    assert parse_io_phs("===\n\nfoo bar\n   \n") == []


def test_classify_protocols_greatescape_breakdown():
    """classify_protocols 把 greatescape 的 12 个协议分到 3 类."""
    parsed = parse_io_phs(SAMPLE_IO_PHS)
    bd = classify_protocols(parsed)

    # 总数（取自 frame 行）
    assert bd.total_frames == 2756
    assert bd.total_bytes == 935469

    # 加密：tls (913 + 97 = 1010 frames)
    cipher_names = [c[0] for c in bd.cipher_protocols]
    assert "tls" in cipher_names
    assert "tls" in bd.per_protocol  # 协议出现在 per_protocol

    # 明文辅助：ftp / ftp-data / http / smtp
    plaintext_names = [p[0] for p in bd.plaintext_aux_protocols]
    assert set(plaintext_names) >= {"ftp", "ftp-data", "http", "smtp"}

    # 占比（cipher ≈ 1010/2756 = 36.6%；plaintext ≈ (46+16+1+33)/2756 ≈ 3.5%）
    assert 35.0 < bd.cipher_pct < 38.0
    assert 3.0 < bd.plaintext_pct < 5.0


def test_classify_protocols_no_cipher():
    """全明文（无 TLS）→ cipher_pct = 0, has_cipher = False."""
    sample = """\
frame                                    frames:100 bytes:50000
  ip                                   frames:100 bytes:50000
    tcp                                frames:100 bytes:50000
      http                             frames:50 bytes:25000
      ftp                              frames:30 bytes:15000
"""
    parsed = parse_io_phs(sample)
    bd = classify_protocols(parsed)
    assert not bd.has_cipher
    assert bd.has_plaintext_aux
    assert bd.cipher_pct == 0.0


def test_classify_protocols_no_plaintext_aux():
    """全加密（无明文辅助）→ has_plaintext_aux = False."""
    sample = """\
frame                                    frames:500 bytes:300000
  ip                                   frames:500 bytes:300000
    tcp                                frames:500 bytes:300000
      tls                              frames:500 bytes:300000
"""
    parsed = parse_io_phs(sample)
    bd = classify_protocols(parsed)
    assert bd.has_cipher
    assert not bd.has_plaintext_aux
    assert bd.cipher_pct == 100.0


def test_classify_protocols_empty():
    """空输入 → 全 0 / 空列表."""
    bd = classify_protocols([])
    assert bd.total_frames == 0
    assert not bd.has_cipher
    assert not bd.has_plaintext_aux


def test_classify_protocols_skips_link_layer():
    """链路层（frame/sll/ip/tcp/udp）不进 per_protocol / 分类."""
    parsed = parse_io_phs(SAMPLE_IO_PHS)
    bd = classify_protocols(parsed)
    for p in LINK_LAYER_PROTOCOLS:
        assert p not in bd.per_protocol
    # 应用层协议进了
    assert "tls" in bd.per_protocol
    assert "ftp" in bd.per_protocol


def test_pretty_print_includes_cipher_and_plaintext():
    """pretty_print 输出含 'Cipher' 和 'Plaintext auxiliary' 标签."""
    parsed = parse_io_phs(SAMPLE_IO_PHS)
    bd = classify_protocols(parsed)
    text = bd.pretty_print()
    assert "Cipher protocols" in text
    assert "Plaintext auxiliary protocols" in text
    assert "Total:" in text


def test_white_lists_not_empty():
    """3 个白名单都非空（健壮性兜底）."""
    assert len(CIPHER_PROTOCOLS) > 0
    assert len(PLAINTEXT_AUX_PROTOCOLS) > 0
    assert len(LINK_LAYER_PROTOCOLS) > 0


def test_classify_protocols_sorts_by_frames_desc():
    """分类结果按 frames 降序."""
    parsed = parse_io_phs(SAMPLE_IO_PHS)
    bd = classify_protocols(parsed)
    for i in range(len(bd.cipher_protocols) - 1):
        assert bd.cipher_protocols[i][1] >= bd.cipher_protocols[i + 1][1]
