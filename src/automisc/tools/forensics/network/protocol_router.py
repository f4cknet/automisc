"""pcap 协议路由 adapter（v0.5-pcap-protocol-router 核心）

整合 protocol_classifier + key_finder，给 pcap 文件一站式：
1. 协议分布解析（tshark -q -z io,phs）
2. 分类（cipher / plaintext_aux / other）
3. 从明文辅助协议找 TLS key 候选（FTP STOR / HTTP URI）
4. 输出 SuspiciousPoint（severity=4，因为还要用户确认）

**不**做（per upgrade/v0.5-pcap-protocol-router.md §2 Q3）：
- 不自动 dump key 文件（凭据敏感）
- 不自动解密 TLS
- 只输出命令模板给用户在 Wireshark 手动操作
"""
from __future__ import annotations

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter
from automisc.tools.forensics.network.key_finder import (
    KeyFinderResult,
    find_key_candidates_from_ftp,
    find_key_candidates_from_http,
    has_ftp_data_traffic,
    merge_candidates,
)
from automisc.tools.forensics.network.protocol_classifier import (
    classify_protocols,
    parse_io_phs,
)


# Wireshark 手动解密命令模板（per upgrade/v0.5-pcap-protocol-router.md §1.3 / §4.3）
def build_wireshark_hint(pcap_path: str, key_filename: str) -> str:
    """生成 Wireshark 手动解密命令模板.

    Args:
        pcap_path: 原始 pcap 路径
        key_filename: key 候选文件名（仅用于提示用户从 FTP-DATA 提取）

    Returns:
        多行命令模板字符串
    """
    return (
        f"# Wireshark 手动解密流程（automisc 不自动解密 — 凭据敏感）\n"
        f"# 1. 从 FTP-DATA 流提取 key 文件：\n"
        f"#    tshark -r {pcap_path} -q -z follow,tcp,raw,<stream_id> > {key_filename}\n"
        f"# 2. 用 tshark --ssl.keys 解密：\n"
        f'#    tshark -r {pcap_path} -o "tls.keys_list:<server_ip>,<port>,http,<key_path>" \\\n'
        f'#      -Y "http contains FLAG" -T fields -e http.request.uri -e http.file_data\n'
        f"# 3. Wireshark GUI：Edit → Preferences → Protocols → TLS → RSA keys list\n"
        f'#    "RSA Keys" 列: <server_ip>,<port>,http,<key_path>\n'
    )


@register_tool
class PcapProtocolRouterAdapter(ToolAdapter):
    """pcap 协议路由 adapter — 协议分类 + TLS key 候选发现."""

    name = "pcap_protocol_router"
    category = "forensics_network"
    description = (
        "pcap 协议层路由：识别 cipher / plaintext_aux 协议分布，"
        "从明文流量（FTP/HTTP/SMTP）找 TLS key 候选文件，"
        "输出 Wireshark 手动解密命令模板"
    )

    default_timeout = 60.0

    def run(self, file_path: str) -> ToolResult:
        """1 步跑完：协议分类 + key 候选发现 + 命令模板生成."""
        tshark = self.binary_path or "tshark"

        # Step 1: 协议分布
        cmd_phs = [tshark, "-r", file_path, "-q", "-z", "io,phs"]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd_phs)

        suspicious: list[SuspiciousPoint] = []
        breakdown = None

        if exit_code == 0 and stdout.strip():
            parsed = parse_io_phs(stdout)
            breakdown = classify_protocols(parsed)

            # 协议分布本身也是信息（severity=1，info 级）
            suspicious.append(SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="protocol_breakdown",
                matched_pattern=breakdown.pretty_print(),
                severity=1,
                suggested_action=(
                    f"识别到 {len(breakdown.cipher_protocols)} 个加密主协议, "
                    f"{len(breakdown.plaintext_aux_protocols)} 个明文辅助协议"
                ),
            ))

            # Step 2: 仅当 cipher 存在 + 有 plaintext_aux 时找 key 候选
            if breakdown.has_cipher and breakdown.has_plaintext_aux:
                # 抓 FTP 控制流
                cmd_ftp = [tshark, "-r", file_path, "-Y", "ftp"]
                ftp_exit, ftp_stdout, ftp_stderr, _ = self._run_subprocess(cmd_ftp)
                ftp_candidates = find_key_candidates_from_ftp(ftp_stdout) if ftp_exit == 0 else []

                # 抓 HTTP 控制流
                cmd_http = [tshark, "-r", file_path, "-Y", "http"]
                http_exit, http_stdout, http_stderr, _ = self._run_subprocess(cmd_http)
                http_candidates = find_key_candidates_from_http(http_stdout) if http_exit == 0 else []

                all_candidates = merge_candidates(ftp_candidates, http_candidates)

                # Step 3: 检查 FTP-DATA 是否存在
                ftp_data_present, ftp_data_bytes = has_ftp_data_traffic(breakdown.per_protocol)

                # 输出 key 候选为 SuspiciousPoint（severity=4）
                if all_candidates:
                    filenames = ", ".join(c.filename for c in all_candidates)
                    hint = build_wireshark_hint(file_path, all_candidates[0].filename)
                    suggested = (
                        f"发现 {len(all_candidates)} 个 TLS key 候选: {filenames}\n"
                        f"FTP-DATA 流量: {ftp_data_bytes} bytes\n"
                        f"\n{hint}"
                    )
                    suspicious.append(SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="tls_key_candidate",
                        offset=None,
                        matched_pattern="; ".join(c.matched_pattern for c in all_candidates),
                        severity=4,
                        suggested_action=suggested,
                        context=f"ftp_data_bytes={ftp_data_bytes}",
                    ))

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout if stdout else "",
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
            metadata={
                "breakdown_summary": (
                    f"cipher={breakdown.cipher_pct:.1f}%, "
                    f"plaintext_aux={breakdown.plaintext_pct:.1f}%"
                ) if breakdown else "",
            } if breakdown else {},
        )


__all__ = [
    "PcapProtocolRouterAdapter",
    "build_wireshark_hint",
]
