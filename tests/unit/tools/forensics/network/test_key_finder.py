"""测试 tools/forensics/network/key_finder.py"""
from __future__ import annotations

import pytest

from automisc.tools.forensics.network.key_finder import (
    TLS_KEY_SUFFIXES,
    find_key_candidates_from_ftp,
    find_key_candidates_from_http,
    has_ftp_data_traffic,
    merge_candidates,
)


# ---------- 真实 FTP 抓包输出 (greatescape.pcap) ----------
SAMPLE_FTP_STDOUT = """\
    1   0.000000  172.17.0.3 → 172.17.42.1 FTP 82 Response: 220---------- Welcome to Pure-FTPd [privsep] [TLS] ----------
    2   0.000123  172.17.42.1 → 172.17.0.3 FTP 74 Request: USER bob
    3   0.000456  172.17.0.3 → 172.17.42.1 FTP 96 Response: 331 User bob OK. Password required
    4   0.000789  172.17.42.1 → 172.17.0.3 FTP 70 Request: PASS toto123
    5   0.001000  172.17.0.3 → 172.17.42.1 FTP 95 Response: 230 OK. Current directory is /
    6   0.001500  172.17.42.1 → 172.17.0.3 FTP 60 Request: SYST
    7   0.001800  172.17.0.3 → 172.17.42.1 FTP 50 Response: 215 UNIX Type: L8
    8   0.002100  172.17.42.1 → 172.17.0.3 FTP 60 Request: TYPE I
    9   0.002400  172.17.0.3 → 172.17.42.1 FTP 50 Response: 200 TYPE is now 8-bit binary
   10   0.002700  172.17.42.1 → 172.17.0.3 FTP 70 Request: PORT 172,17,42,1,171,159
   11   0.003000  172.17.0.3 → 172.17.42.1 FTP 100 Response: 200 PORT command successful
   12   0.003500  172.17.42.1 → 172.17.0.3 FTP 60 Request: STOR ssc.key
   13   0.004000  172.17.0.3 → 172.17.42.1 FTP 120 Response: 150 Connecting to port 43935
   14   0.010000  172.17.0.3 → 172.17.42.1 FTP 100 Response: 226-File successfully transferred
   15   0.020000  172.17.42.1 → 172.17.0.3 FTP 60 Request: QUIT
   16   0.021000  172.17.0.3 → 172.17.42.1 FTP 80 Response: 221-Goodbye. You uploaded 4 and downloaded 0 kbytes.
"""


# ---------- FTP STOR 解析 ----------

def test_find_ftp_stor_extracts_ssc_key():
    """真实场景：从 FTP STOR ssc.key 提取 key 候选."""
    candidates = find_key_candidates_from_ftp(SAMPLE_FTP_STDOUT)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.filename == "ssc.key"
    assert c.suffix == ".key"
    assert c.source_protocol == "ftp"
    assert c.transfer_direction == "upload"
    assert "STOR ssc.key" in c.matched_pattern


def test_find_ftp_stor_ignores_non_key_files():
    """FTP 传非 key 文件（如 .txt）不被识别为候选."""
    sample = """\
    1   0.0 FTP Request: STOR readme.txt
    2   0.0 FTP Request: STOR data.csv
    3   0.0 FTP Request: STOR image.png
"""
    candidates = find_key_candidates_from_ftp(sample)
    assert candidates == []


def test_find_ftp_stor_handles_pem_and_crt():
    """其他 key 后缀（.pem / .crt / .pub）也命中."""
    sample = """\
    1   0.0 FTP Request: STOR server.pem
    2   0.0 FTP Request: STOR ca.crt
    3   0.0 FTP Request: STOR id_rsa.pub
    4   0.0 FTP Request: STOR cert.p12
"""
    candidates = find_key_candidates_from_ftp(sample)
    filenames = sorted(c.filename for c in candidates)
    assert filenames == ["ca.crt", "cert.p12", "id_rsa.pub", "server.pem"]


def test_find_ftp_stor_handles_retr_download():
    """RETR (下载) 也识别为 key 候选."""
    sample = "    1   0.0 FTP Request: RETR private.key\n"
    candidates = find_key_candidates_from_ftp(sample)
    assert len(candidates) == 1
    assert candidates[0].transfer_direction == "download"
    assert candidates[0].filename == "private.key"


def test_find_ftp_stor_handles_path_prefix():
    """文件名带路径前缀（subdir/key.pem）也能识别后缀."""
    sample = "    1   0.0 FTP Request: STOR keys/server.pem\n"
    candidates = find_key_candidates_from_ftp(sample)
    assert len(candidates) == 1
    assert candidates[0].filename == "keys/server.pem"


def test_find_ftp_stor_empty_input():
    """空输入返回空列表."""
    assert find_key_candidates_from_ftp("") == []


def test_find_ftp_stor_case_insensitive_suffix():
    """后缀大小写不敏感（.KEY / .Key / .key 都命中）."""
    sample = """\
    1   0.0 FTP Request: STOR UPPER.KEY
    2   0.0 FTP Request: STOR mixed.Key
"""
    candidates = find_key_candidates_from_ftp(sample)
    assert len(candidates) == 2
    # 后缀保留原始大小写
    suffixes = sorted(c.suffix for c in candidates)
    assert suffixes == [".KEY", ".Key"]


# ---------- HTTP URI 解析 ----------

def test_find_http_uri_extracts_key_path():
    """HTTP GET /path/to/server.key 命中."""
    sample = """\
    1   0.0 HTTP Request: GET /admin/server.key HTTP/1.1
    2   0.0 HTTP Request: POST /upload/ca.pem HTTP/1.1
"""
    candidates = find_key_candidates_from_http(sample)
    assert len(candidates) == 2
    paths = sorted(c.filename for c in candidates)
    assert paths == ["/admin/server.key", "/upload/ca.pem"]


def test_find_http_uri_ignores_normal_paths():
    """普通 URL 不命中."""
    sample = """\
    1   0.0 HTTP Request: GET /index.html HTTP/1.1
    2   0.0 HTTP Request: GET /api/users HTTP/1.1
    3   0.0 HTTP Request: POST /login HTTP/1.1
"""
    assert find_key_candidates_from_http(sample) == []


def test_find_http_uri_handles_all_suffixes():
    """白名单 10 个后缀 HTTP 都识别."""
    suffixes_to_test = ["key", "pub", "pem", "crt", "cer", "der", "p12", "pfx", "pkcs8", "openssh"]
    sample = "\n".join(f"    1   0.0 HTTP Request: GET /files/test.{suf} HTTP/1.1" for suf in suffixes_to_test)
    candidates = find_key_candidates_from_http(sample)
    assert len(candidates) == 10


# ---------- FTP-DATA 检测 ----------

def test_has_ftp_data_traffic_true():
    """per_protocol 含 ftp-data 且 frames > 0 → True."""
    per = {"ftp-data": (1, 3341), "ftp": (16, 1828), "tls": (913, 621804)}
    has, bytes_ = has_ftp_data_traffic(per)
    assert has is True
    assert bytes_ == 3341


def test_has_ftp_data_traffic_false_when_absent():
    """per_protocol 不含 ftp-data → False."""
    per = {"ftp": (16, 1828), "http": (46, 30901)}
    has, bytes_ = has_ftp_data_traffic(per)
    assert has is False
    assert bytes_ == 0


def test_has_ftp_data_traffic_false_when_zero_frames():
    """ftp-data frames=0 → False（空流）."""
    per = {"ftp-data": (0, 0)}
    has, _ = has_ftp_data_traffic(per)
    assert has is False


# ---------- merge_candidates ----------

def test_merge_candidates_dedup_by_filename_and_source():
    """同 (filename, source_protocol) 去重保首个."""
    c1 = find_key_candidates_from_ftp("    1   0.0 FTP Request: STOR ssc.key\n")[0]
    c2 = find_key_candidates_from_ftp("    2   0.0 FTP Request: STOR ssc.key\n")[0]  # 同名重复
    merged = merge_candidates([c1], [c2])
    assert len(merged) == 1


def test_merge_candidates_different_sources_kept():
    """不同 source_protocol 都保留（FTP / HTTP 同一文件名当不同候选）."""
    ftp_c = find_key_candidates_from_ftp("    1   0.0 FTP Request: STOR server.key\n")[0]
    http_c = find_key_candidates_from_http("    1   0.0 HTTP Request: GET /server.key HTTP/1.1\n")[0]
    merged = merge_candidates([ftp_c], [http_c])
    assert len(merged) == 2


def test_merge_candidates_empty_inputs():
    """空输入返回空."""
    assert merge_candidates([], []) == []
    assert merge_candidates() == []


# ---------- 后缀白名单 ----------

def test_suffix_whitelist_count():
    """白名单 ≥ 10 个后缀（per Owner Q2）."""
    assert len(TLS_KEY_SUFFIXES) >= 10


def test_suffix_whitelist_contains_core_set():
    """核心后缀都在白名单."""
    required = {".key", ".pub", ".pem", ".crt"}
    assert required <= TLS_KEY_SUFFIXES
