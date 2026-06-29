"""qemu_img_extract adapter (per v0.5-qemu-img-adapter spec, Owner 2026-06-29 23:23 拍 B).

实战 vmdk → raw 转换 (per v0.5-train-018 flag.vmdk 走 qemu-img convert).
GUI 工具栏 '🖼️ qemu-img 转换' 入口, 不挂 auto-run (per AGENTS §1 铁律 7 写盘).

输出: <input_stem>__qemu_img_raw/<input_stem>.raw (per v0.5-output-samedir).
跟 sevenz_extract 模式 (extract_dir_for helper + shutil.rmtree 清理).
"""
from pathlib import Path

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter
from automisc.core.utils.output_path import extract_dir_for
# fix_qemu_img_friendly_error: 共享 _binary_not_found_result helper (per qemu_img.py)
from automisc.tools.misc.archive.qemu_img import _binary_not_found_result


@register_tool
class QemuImgExtractAdapter(ToolAdapter):
    """`qemu_img_extract` adapter — qemu-img convert 虚拟磁盘转换 (vmdk → raw 写盘, GUI 工具栏手工)."""

    name = "qemu_img_extract"
    category = "archive"
    description = (
        "qemu-img convert 虚拟磁盘转换 (vmdk → raw 写盘, GUI 工具栏手工, 不挂 auto-run)"
    )

    default_timeout = 120.0  # 大文件转换可能慢, 实战给 120s 兜底

    def run(self, file_path: str) -> ToolResult:
        # v0.5-qemu-img-adapter: 走 resolve_tool_binary
        from automisc.tools.paths import resolve_tool_binary
        qemu_img_bin = self.binary_path or resolve_tool_binary("qemu-img")

        # fix_qemu_img_friendly_error (2026-06-29 23:40 Owner 实战触发):
        #   qemu-img 未装 → 不 mkdir 空目录, 不跑 convert 崩, 直接 emit 友好 SP
        #   (写盘前预检, 避免 Path.mkdir() 后 subprocess FileNotFoundError 残留空目录)
        if not qemu_img_bin:
            return _binary_not_found_result(self.name, file_path, binary_name="qemu-img")

        # 1. 准备 output 目录 (per v0.5-output-samedir)
        extract_dir = extract_dir_for(file_path, purpose="qemu_img_raw")
        if extract_dir.exists():
            # qemu-img convert 不覆盖, 先清旧的
            import shutil
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        output_raw = extract_dir / f"{Path(file_path).stem}.raw"

        # 2. 构造 qemu-img convert 命令 (per v0.5-train-018 实战)
        #    默认 -f vmdk -O raw, 实战 flag.vmdk 走 vmdk → raw
        #    进阶: 留 -f/-O 透传 (v0.5+ 实战覆盖 qcow2/raw 时加, per spec §6 Q5)
        cmd = [
            qemu_img_bin,
            "convert",
            "-f", "vmdk",     # TODO v0.5+: 自动探测 (info 一次拿 fmt)
            "-O", "raw",
            file_path,
            str(output_raw),
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd, timeout=self.default_timeout)

        suspicious: list[SuspiciousPoint] = []

        # 1. 通用扫描 (owner 铁律: 关键字命中 = 可疑)
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 成功信号: 退出码 0 + output raw 存在
        #    (per v0.5-sevenz-extract 模式, archive_extracted sev=5 关键成功)
        metadata: dict = {"extract_dir": str(extract_dir)}
        if exit_code == 0 and output_raw.exists():
            size = output_raw.stat().st_size
            suspicious.append(SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category="vdisk_extracted",
                offset=None,
                matched_pattern=f"qemu-img 转换 vmdk → raw, {size} bytes → {output_raw}",
                severity=5,  # 关键成功信号 (per v0.5-sevenz-extract 模式)
                suggested_action=(
                    f"qemu-img 转换成功, output: {output_raw} — "
                    f"用 foremost 雕 (per v0.5-train-018 实战路径)"
                ),
            ))
            # v0.5-hex-router-journal: written_files metadata
            metadata["written_files"] = [{
                "path": str(output_raw),
                "kind": "raw vdisk",
                "source": self.name,
            }]

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            metadata=metadata,
        )


__all__ = ["QemuImgExtractAdapter"]
