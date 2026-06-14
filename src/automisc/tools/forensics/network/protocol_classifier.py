"""协议分类器（v0.5-pcap-protocol-router 核心）

解析 tshark `io,phs`（Protocol Hierarchy Statistics）输出，识别 pcap 里的协议分布，
把协议分到 3 类：
- **加密主协议**（cipher）：TLS / HTTPS / FTPS / SMTPS — 需要 key 才能解
- **明文辅助协议**（plaintext_aux）：FTP / HTTP(80) / SMTP(25) / Telnet / TFTP / SNMP — 候选 key 藏身处
- **其他**：不归类（eth/ip/tcp/udp/sll 等链路层；HTTP 走 443 算 cipher；OCSP 算其他）

**设计原则**（per upgrade/v0.5-pcap-protocol-router.md §2 Q1）：
- 不依赖 LLM / 启发式复杂判断
- 协议名命中白名单即分类
- 输出结构化 dict 供 chain 下游使用
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------- 协议白名单（v0.5-pcap-protocol-router 决策） ----------

# 加密主协议：默认需要 key 才能解
CIPHER_PROTOCOLS: frozenset[str] = frozenset({
    "tls",        # TLS 1.0/1.1/1.2/1.3
    "ssl",        # 旧 SSL
    "https",      # HTTPS (tshark 把 443 直接解析为 https)
    "ftps",       # FTPS (990)
    "smtps",      # SMTPS (465)
    "imaps",      # IMAPS (993)
    "pop3s",      # POP3S (995)
    "rdps",       # RDPS
    "ssh",        # SSH (虽然不是 key 候选但属于加密流)
})

# 明文辅助协议：key 候选藏身处
PLAINTEXT_AUX_PROTOCOLS: frozenset[str] = frozenset({
    "ftp",        # FTP 控制连接
    "ftp-data",   # FTP 数据连接（关键！藏 key 文件本体）
    "http",       # HTTP 明文（80）
    "smtp",       # SMTP 明文（25）
    "imap",       # IMAP 明文（143）
    "pop3",       # POP3 明文（110）
    "telnet",     # Telnet
    "tftp",       # TFTP
    "snmp",       # SNMP（v1/v2c 社区名可作 key hint）
})

# 链路层 / 传输层（不归类，跳过）
LINK_LAYER_PROTOCOLS: frozenset[str] = frozenset({
    "frame", "eth", "sll", "ip", "ipv6", "tcp", "udp", "icmp", "icmpv6",
    "arp", "vlan", "mpls", "pppoe", "ipx", "stp", "llc",
})


# ---------- tshark -q -z io,phs 输出解析 ----------

# 示例输出:
#   frame                                    frames:2756 bytes:935469
#     ip                                   frames:2756 bytes:935469
#       tcp                                frames:2756 bytes:935469
#         tls                              frames:913 bytes:621804
#         ftp                              frames:16 bytes:1828
#
# 缩进 = 协议层嵌套（每层 2 空格）；最后一列是 frames/bytes
_PROTO_LINE_RE = re.compile(r"^(\s*)([\w-]+)\s+frames:(\d+)\s+bytes:(\d+)\s*$")


def parse_io_phs(stdout: str) -> list[tuple[str, int, int]]:
    """解析 tshark -q -z io,phs 输出。

    Returns:
        list of (proto_name, frames, bytes) — 顺序保留（链路层优先，嵌套应用层在后）
    """
    result: list[tuple[str, int, int]] = []
    for line in stdout.splitlines():
        m = _PROTO_LINE_RE.match(line)
        if not m:
            continue
        _, proto, frames, bytes_ = m.groups()
        result.append((proto, int(frames), int(bytes_)))
    return result


@dataclass
class ProtocolBreakdown:
    """协议占比 + 加密/明文分类结果（per v0.5-pcap-protocol-router §3.1）.

    Attributes:
        total_frames: pcap 总包数（链路层第一行）
        total_bytes: pcap 总字节数
        per_protocol: {proto_name: (frames, bytes)} — 排除链路层
        cipher_protocols: 加密主协议列表（按 frames 降序）
        plaintext_aux_protocols: 明文辅助协议列表（按 frames 降序）
        other_protocols: 其他协议列表（按 frames 降序）
        cipher_pct: 加密主协议 frames 占比 (0.0 - 100.0)
        plaintext_pct: 明文辅助协议 frames 占比 (0.0 - 100.0)
    """
    total_frames: int = 0
    total_bytes: int = 0
    per_protocol: dict[str, tuple[int, int]] = field(default_factory=dict)
    cipher_protocols: list[tuple[str, int, int]] = field(default_factory=list)
    plaintext_aux_protocols: list[tuple[str, int, int]] = field(default_factory=list)
    other_protocols: list[tuple[str, int, int]] = field(default_factory=list)
    cipher_pct: float = 0.0
    plaintext_pct: float = 0.0

    @property
    def has_cipher(self) -> bool:
        """是否含加密主协议流量。"""
        return bool(self.cipher_protocols)

    @property
    def has_plaintext_aux(self) -> bool:
        """是否含明文辅助协议流量（key 候选藏身处）。"""
        return bool(self.plaintext_aux_protocols)

    def pretty_print(self) -> str:
        """人类可读的协议分布输出（GUI / journal 用）。"""
        lines: list[str] = []
        lines.append(f"Total: {self.total_frames} frames, {self.total_bytes} bytes")
        lines.append("")
        if self.cipher_protocols:
            lines.append("Cipher protocols (需要 key 解密):")
            for name, frames, bytes_ in self.cipher_protocols:
                pct = 100.0 * frames / self.total_frames if self.total_frames else 0.0
                lines.append(f"  {name:20s} {frames:>6d} pkts ({pct:5.1f}%)  {bytes_:>10d} bytes")
        if self.plaintext_aux_protocols:
            lines.append("")
            lines.append("Plaintext auxiliary protocols (key 候选藏身处):")
            for name, frames, bytes_ in self.plaintext_aux_protocols:
                pct = 100.0 * frames / self.total_frames if self.total_frames else 0.0
                lines.append(f"  {name:20s} {frames:>6d} pkts ({pct:5.1f}%)  {bytes_:>10d} bytes")
        if self.other_protocols:
            lines.append("")
            lines.append("Other protocols:")
            for name, frames, bytes_ in self.other_protocols[:10]:  # 限 10 行
                pct = 100.0 * frames / self.total_frames if self.total_frames else 0.0
                lines.append(f"  {name:20s} {frames:>6d} pkts ({pct:5.1f}%)")
        return "\n".join(lines)


def classify_protocols(parsed: list[tuple[str, int, int]]) -> ProtocolBreakdown:
    """把 parse_io_phs 结果分到 3 类。

    Args:
        parsed: parse_io_phs 返回的 (proto, frames, bytes) 列表

    Returns:
        ProtocolBreakdown 含完整分类
    """
    if not parsed:
        return ProtocolBreakdown()

    # 第一行通常是 frame（含总包数/总字节数）
    first_proto, first_frames, first_bytes = parsed[0]
    total_frames = first_frames
    total_bytes = first_bytes

    per_protocol: dict[str, tuple[int, int]] = {}
    cipher: list[tuple[str, int, int]] = []
    plaintext: list[tuple[str, int, int]] = []
    other: list[tuple[str, int, int]] = []

    for proto, frames, bytes_ in parsed:
        proto_lower = proto.lower()
        # 链路层 + 传输层跳过（不计入 per_protocol）
        if proto_lower in LINK_LAYER_PROTOCOLS:
            continue
        per_protocol[proto] = (frames, bytes_)
        if proto_lower in CIPHER_PROTOCOLS:
            cipher.append((proto, frames, bytes_))
        elif proto_lower in PLAINTEXT_AUX_PROTOCOLS:
            plaintext.append((proto, frames, bytes_))
        else:
            other.append((proto, frames, bytes_))

    # 排序：按 frames 降序
    cipher.sort(key=lambda x: -x[1])
    plaintext.sort(key=lambda x: -x[1])
    other.sort(key=lambda x: -x[1])

    # 占比（基于 total_frames）
    cipher_pct = 100.0 * sum(f for _, f, _ in cipher) / total_frames if total_frames else 0.0
    plaintext_pct = 100.0 * sum(f for _, f, _ in plaintext) / total_frames if total_frames else 0.0

    return ProtocolBreakdown(
        total_frames=total_frames,
        total_bytes=total_bytes,
        per_protocol=per_protocol,
        cipher_protocols=cipher,
        plaintext_aux_protocols=plaintext,
        other_protocols=other,
        cipher_pct=cipher_pct,
        plaintext_pct=plaintext_pct,
    )


__all__ = [
    "CIPHER_PROTOCOLS",
    "PLAINTEXT_AUX_PROTOCOLS",
    "LINK_LAYER_PROTOCOLS",
    "parse_io_phs",
    "classify_protocols",
    "ProtocolBreakdown",
]
