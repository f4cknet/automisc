"""Key 候选发现器（v0.5-pcap-protocol-router 核心）

从明文辅助协议（FTP / HTTP / SMTP）的流量里发现疑似 TLS private key 的文件传输。

**检测策略**（per upgrade/v0.5-pcap-protocol-router.md §2 Q2）：
1. **FTP STOR 命令**：从 FTP 控制流 grep `STOR <文件名>`，文件名命中 TLS key 后缀白名单
2. **HTTP URI**：从 HTTP request URI 提取 `/xxx.key` 等路径
3. **FTP-DATA 流**：从 io,phs 看 ftp-data 流量大小，标记"存在数据传输"

**不**做的事（per §2 Q3）：
- 不自动 dump key 文件（凭据敏感）
- 不自动解密 TLS
- 只输出 key 候选清单 + 提示用户去 Wireshark 手动配
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# TLS private key 后缀白名单（per upgrade/v0.5-pcap-protocol-router.md §4.2）
TLS_KEY_SUFFIXES: frozenset[str] = frozenset({
    ".key",      # 通用
    ".pub",      # SSH public key
    ".pem",      # PEM 编码
    ".crt",      # 证书
    ".cer",      # 证书（DER）
    ".der",      # DER 编码
    ".p12",      # PKCS12
    ".pfx",      # PKCS12（旧）
    ".pkcs8",    # PKCS8
    ".openssh",  # OpenSSH 私钥
})

# ---------- 解析器 ----------

# FTP 控制流 STOR 命令（兼容 tshark -T fields -e _ws.col.Info 输出格式）
#   "    12   0.003500  172.17.42.1 → 172.17.0.3 FTP 60 Request: STOR ssc.key"
# 也兼容 grep 后的纯行：
#   "Request: STOR ssc.key"
_FTP_STOR_RE = re.compile(
    r"Request:\s+STOR\s+(\S+)",
)

# FTP 控制流 RETR 命令
_FTP_RETR_RE = re.compile(
    r"Request:\s+RETR\s+(\S+)",
)

# HTTP request URI 提取（兼容 tshark -T fields 输出 + 纯行）
_HTTP_URI_RE = re.compile(
    r"Request:\s+(?:GET|POST|PUT)\s+(\S+\.(?:key|pub|pem|crt|cer|der|p12|pfx|pkcs8|openssh))(?:\s+HTTP/\S+)?",
    re.IGNORECASE,
)

# 找文件名后缀
def _ends_with_key_suffix(name: str) -> str | None:
    """返回命中的后缀（保留原始大小写）；没命中返回 None.

    匹配时小写化比较；返回原始大小写的后缀供展示。
    """
    name_lower = name.lower()
    for suf in TLS_KEY_SUFFIXES:
        if name_lower.endswith(suf):
            # 从原始 name 末尾截出原大小写后缀
            return name[-len(suf):]
    return None


@dataclass
class KeyCandidate:
    """单个 key 候选.

    Attributes:
        filename: 文件名（原始大小写）
        suffix: 命中的后缀（带点）
        source_protocol: 协议来源（ftp / http / ftp-data）
        transfer_direction: 'upload' (STOR) / 'download' (RETR) / 'http' / 'unknown'
        matched_pattern: 原始匹配字符串（GUI/journal 展示用）
    """
    filename: str
    suffix: str
    source_protocol: str
    transfer_direction: str
    matched_pattern: str

    @property
    def display(self) -> str:
        """一行展示格式。"""
        return (
            f"{self.source_protocol:10s} {self.transfer_direction:8s} "
            f"{self.filename!r:40s} (suffix={self.suffix})"
        )


@dataclass
class KeyFinderResult:
    """KeyFinder 整体输出.

    Attributes:
        candidates: 候选列表
        ftp_data_present: FTP-DATA 流量是否存在（用于提示 "see FTP-DATA stream N"）
        ftp_data_bytes: FTP-DATA 总字节数
    """
    candidates: list[KeyCandidate] = field(default_factory=list)
    ftp_data_present: bool = False
    ftp_data_bytes: int = 0

    @property
    def has_candidates(self) -> bool:
        return bool(self.candidates)

    def pretty_print(self) -> str:
        lines: list[str] = []
        if self.candidates:
            lines.append(f"Found {len(self.candidates)} TLS key candidate(s):")
            for c in self.candidates:
                lines.append(f"  - {c.display}")
        else:
            lines.append("No TLS key candidate found in plaintext auxiliary protocols.")
        if self.ftp_data_present:
            lines.append(
                f"\nFTP-DATA traffic present: {self.ftp_data_bytes} bytes. "
                f"Check tcp.stream for actual file transfer payload "
                f"(use: tshark -q -z follow,tcp,raw,<stream_id>)."
            )
        return "\n".join(lines)


def find_key_candidates_from_ftp(ftp_stdout: str) -> list[KeyCandidate]:
    """从 tshark -Y ftp 的输出里提取 STOR / RETR 命令中的 key 候选.

    Args:
        ftp_stdout: tshark -Y ftp -T fields ... 或 -V 的输出文本

    Returns:
        KeyCandidate 列表
    """
    candidates: list[KeyCandidate] = []
    # STOR = upload (client → server)
    for m in _FTP_STOR_RE.finditer(ftp_stdout):
        filename = m.group(1)
        suf = _ends_with_key_suffix(filename)
        if suf:
            candidates.append(KeyCandidate(
                filename=filename,
                suffix=suf,
                source_protocol="ftp",
                transfer_direction="upload",
                matched_pattern=m.group(0).strip(),
            ))
    # RETR = download (server → client)
    for m in _FTP_RETR_RE.finditer(ftp_stdout):
        filename = m.group(1)
        suf = _ends_with_key_suffix(filename)
        if suf:
            candidates.append(KeyCandidate(
                filename=filename,
                suffix=suf,
                source_protocol="ftp",
                transfer_direction="download",
                matched_pattern=m.group(0).strip(),
            ))
    return candidates


def find_key_candidates_from_http(http_stdout: str) -> list[KeyCandidate]:
    """从 tshark -Y http 的输出里提取 URI 中的 key 候选.

    Args:
        http_stdout: tshark -Y http -T fields ... 或 -V 的输出

    Returns:
        KeyCandidate 列表
    """
    candidates: list[KeyCandidate] = []
    for m in _HTTP_URI_RE.finditer(http_stdout):
        uri_path = m.group(1)
        # 取 basename
        basename = uri_path.rsplit("/", 1)[-1] if "/" in uri_path else uri_path
        suf = _ends_with_key_suffix(basename)
        if suf:
            candidates.append(KeyCandidate(
                filename=uri_path,
                suffix=suf,
                source_protocol="http",
                transfer_direction="http",
                matched_pattern=m.group(0).strip(),
            ))
    return candidates


def has_ftp_data_traffic(per_protocol: dict[str, tuple[int, int]]) -> tuple[bool, int]:
    """从 per_protocol dict 检查是否有 ftp-data 流量.

    Args:
        per_protocol: {proto_name: (frames, bytes)}

    Returns:
        (has_ftp_data, bytes) — bytes 是 ftp-data 总字节数
    """
    for proto, (frames, bytes_) in per_protocol.items():
        if proto.lower() == "ftp-data" and frames > 0:
            return True, bytes_
    return False, 0


def merge_candidates(*lists: list[KeyCandidate]) -> list[KeyCandidate]:
    """合并多个候选列表，按 (filename, source_protocol) 去重保首个."""
    seen: set[tuple[str, str]] = set()
    merged: list[KeyCandidate] = []
    for lst in lists:
        for c in lst:
            key = (c.filename, c.source_protocol)
            if key not in seen:
                seen.add(key)
                merged.append(c)
    return merged


__all__ = [
    "TLS_KEY_SUFFIXES",
    "KeyCandidate",
    "KeyFinderResult",
    "find_key_candidates_from_ftp",
    "find_key_candidates_from_http",
    "has_ftp_data_traffic",
    "merge_candidates",
]
