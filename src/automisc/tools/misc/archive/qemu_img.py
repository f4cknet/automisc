"""qemu_img adapter (per v0.5-qemu-img-adapter spec, Owner 2026-06-29 23:23 拍 B).

实战 vmdk/qcow2/raw 等虚拟磁盘格式探测 (per v0.5-train-018 flag.vmdk).
输出 SP: vdisk_format (虚拟磁盘格式识别, sev=3 info 级别).

可挂 auto-run (探测归探测, per AGENTS §1 铁律 7).
跟 sevenz (探测) / sevenz_extract (写盘) 同模式.
"""
from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


@register_tool
class QemuImgAdapter(ToolAdapter):
    """`qemu_img` adapter — qemu-img info 虚拟磁盘探测 (vmdk/qcow2/raw 等格式识别)."""

    name = "qemu_img"
    category = "archive"
    description = (
        "qemu-img info 虚拟磁盘探测 (vmdk/qcow2/raw 等格式识别, 探测归探测, 可挂 auto-run)"
    )

    default_timeout = 30.0  # info 命令快, 30s 实战够

    def run(self, file_path: str) -> ToolResult:
        # v0.5-qemu-img-adapter: 走 resolve_tool_binary (per v0.5-platform-extend-tools 模式)
        from automisc.tools.paths import resolve_tool_binary
        qemu_img_bin = self.binary_path or resolve_tool_binary("qemu-img") or "qemu-img"

        cmd = [qemu_img_bin, "info", file_path]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd, timeout=self.default_timeout)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描 (owner 铁律: 关键字命中 = 可疑)
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 虚拟磁盘格式识别
        #    qemu-img info 输出: "file format: vmdk" / "virtual size: ..."
        for line in stdout.split("\n"):
            line_strip = line.strip()
            if line_strip.lower().startswith("file format:"):
                fmt = line_strip.split(":", 1)[1].strip()
                suspicious.append(SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="vdisk_format",
                    offset=None,
                    matched_pattern=f"qemu-img 识别虚拟磁盘格式: {fmt}",
                    severity=3,  # info 级别 (跟 exiftool 同)
                    suggested_action=(
                        f"虚拟磁盘 {fmt}, 走 GUI 工具栏 '🖼️ qemu-img 转换' 转 raw 后 "
                        f"foremost 雕内嵌文件 (per v0.5-train-018 实战路径)"
                    ),
                ))
                break  # 只识别第 1 个 format, 避免重复 SP

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
        )


__all__ = ["QemuImgAdapter"]
