"""evtx_dump adapter（per ``tools.md`` §3.4）

``python-evtx`` 库：解析 Windows EVTX 日志格式。

**v0.1 范围**（最小可用 — Windows 事件日志）：
- 解析 .evtx 文件为 XML records
- 提取 EventID / Source / TimeCreated / User / Computer
- 检测可疑 EventID：登录失败 (4625) / 特权提升 (4672) / 进程创建 (4688 含命令行) / 服务安装 (7045)
- 限制最大 records（防大 evtx OOM）

**macOS**：``pip install python-evtx``（已装 0.8.1，per PR6）。
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# 可疑 EventID 映射（per Windows Security Auditing 文档）
_SUSPICIOUS_EVENTIDS = {
    4624: (2, "Successful logon"),  # 登录成功
    4625: (5, "Failed logon"),  # 登录失败（强信号：可能爆破）
    4634: (1, "Logoff"),
    4648: (4, "Logon with explicit credentials"),  # 可疑：使用其他凭据
    4672: (3, "Special privileges assigned"),  # 特权登录
    4688: (3, "Process created"),  # 进程创建（含命令行）
    4697: (3, "Service installed"),  # 服务安装
    7045: (5, "Service installed (System log)"),  # 服务安装（system log）
    1102: (5, "Audit log cleared"),  # 审计日志清空（强隐匿信号）
}

# 进程命令行可疑关键字
_CMDLINE_KEYWORDS = [
    "powershell",
    "cmd.exe",
    "whoami",
    "net user",
    "net localgroup",
    "mimikatz",
    "psexec",
    "wmic",
    "base64",
    "-enc",  # powershell encoded command
    "frombase64string",
    "downloadstring",
    "bitsadmin",
    "certutil",
    "regsvr32",
]

# 单文件最大 record 数（防 OOM）
_MAX_RECORDS = 5000

# NS 命名空间（Windows Event Log XML 都在这个 namespace）
_NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}


@register_tool
class EvtxDumpAdapter(ToolAdapter):
    """`python-evtx` adapter —— Windows EVTX 日志解析 + 可疑 EventID 检测。"""

    name = "evtx_dump"
    category = "forensics_log"
    description = "Windows EVTX 日志解析（EventID / 进程命令行 / 登录事件）"

    default_timeout = 60.0

    def run(self, file_path: str) -> ToolResult:
        try:
            import Evtx.Evtx as evtx_mod
        except ImportError as e:
            return ToolResult(
                tool_name=self.name,
                exit_code=127,
                stdout="",
                stderr=f"python-evtx not installed: {e}",
                suspicious_points=[],
                duration_ms=0,
            )

        # 累积所有 record 的 XML 输出（限制条数）
        all_xml: list[str] = []
        try:
            with evtx_mod.Evtx(file_path) as log:
                count = 0
                for record in log.records():
                    if count >= _MAX_RECORDS:
                        break
                    try:
                        xml_str = record.xml()
                        all_xml.append(xml_str)
                    except Exception:  # noqa: BLE001
                        # 损坏的 record 跳过
                        continue
                    count += 1
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                tool_name=self.name,
                exit_code=1,
                stdout="",
                stderr=f"EVTX parse error: {e}",
                suspicious_points=[],
                duration_ms=0,
            )

        # 合并所有 XML
        combined = "\n".join(all_xml)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=combined,
        ))

        # 2. 逐 record 解析
        record_count = 0
        for xml_str in all_xml:
            try:
                root = ET.fromstring(xml_str)
            except ET.ParseError:
                continue
            record_count += 1

            # 提取 EventID + System 字段
            system = root.find("e:System", _NS)
            if system is None:
                continue

            event_id_el = system.find("e:EventID", _NS)
            event_id = int(event_id_el.text) if event_id_el is not None and event_id_el.text else 0

            computer_el = system.find("e:Computer", _NS)
            computer = computer_el.text if computer_el is not None else "?"

            # 检测可疑 EventID
            if event_id in _SUSPICIOUS_EVENTIDS:
                severity, desc = _SUSPICIOUS_EVENTIDS[event_id]

                # EventID 4688（进程创建）特别处理：检测命令行
                cmdline = ""
                if event_id == 4688:
                    data_section = root.find("e:EventData", _NS)
                    if data_section is not None:
                        for data in data_section.findall("e:Data", _NS):
                            if data.get("Name") == "CommandLine":
                                cmdline = data.text or ""
                                break
                        if not cmdline:
                            # 退化：用所有 Data 拼
                            cmdline = " ".join(
                                d.text or "" for d in data_section.findall("e:Data", _NS)
                            )

                    # 命令行命中可疑关键字 → severity 升 1
                    if any(kw in cmdline.lower() for kw in _CMDLINE_KEYWORDS):
                        severity = min(5, severity + 1)
                        suspicious.append(
                            SuspiciousPoint(
                                id="",
                                tool_name=self.name,
                                file_path=file_path,
                                category="log_suspicious_cmdline",
                                offset=None,
                                matched_pattern=f"EventID={event_id} Computer={computer} CommandLine={cmdline[:200]!r}",
                                severity=severity,
                                suggested_action=(
                                    "进程命令行命中可疑关键字（powershell/cmd.exe/mimikatz/-enc 等），"
                                    "建议结合主机调查（process tree / parent PID）"
                                ),
                            )
                        )
                        continue

                # 普通可疑 EventID
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="log_suspicious_eventid",
                        offset=None,
                        matched_pattern=f"EventID={event_id} Computer={computer} ({desc})",
                        severity=severity,
                        suggested_action=desc,
                    )
                )

        # 3. 报告 record 总数
        if record_count > 0:
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="log_meta",
                    offset=None,
                    matched_pattern=f"parsed {record_count} EVTX records (capped at {_MAX_RECORDS})",
                    severity=1,
                    suggested_action="记录 event 总数便于交叉验证",
                )
            )

        return ToolResult(
            tool_name=self.name,
            exit_code=0,
            stdout=combined,
            stderr="",
            suspicious_points=suspicious,
            duration_ms=0,
        )
