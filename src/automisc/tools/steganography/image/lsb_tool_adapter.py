"""lsb_tool adapter (per v0.5-lsb-tool-unify, Phase 3)

**lsb_tool** —— 3 mode 统一 LSB 隐写工具 (替代 lsb_detect + lsb_extract + lsb_bytes_extract).

**auto-run 池替代**:
- `FIND_SUSPICIOUS_PICTURE_TOOLS` 中 `lsb_detect` → `lsb_tool` (per spec §3.9)
- 仍 6 tools (per AGENTS §1 铁律 7: auto-run 不变)

**3 mode** (LSBToolAction 默认 mode='detect', 适配器透传 mode 参数):
- `detect`: readonly 探测 (auto-run 用)
- `extract`: GUI 工具栏抽字节流 (替代 zsteg subprocess, Win 不依赖 Ruby)
- `extract_bytes`: chain `lsb-bytes` 4 参数 (backward compat)

**跟 zsteg adapter 关系**: zsteg adapter 已删除 (per v0.5-lsb-tool-bitplane-preview-matrix Commit 4, Owner Q4=b 拍板);本 lsb_tool adapter 完整替代 zsteg 能力 + 8 bit × 6 perm preview matrix + GUI 工具栏抽字节流.
"""
from __future__ import annotations

import time

from automisc.core.actions.lsb_tool import LSBToolAction
from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


@register_tool
class LsbToolAdapter(ToolAdapter):
    """`lsb_tool` adapter —— 3 mode 统一 LSB 隐写工具.

    per spec §3.1 模块位置: tools/steganography/image/lsb_tool_adapter.py
    per spec §3.1 双注册: tools/__init__.py + steganography/image/ (namespace package)
    """

    name = "lsb_tool"
    category = "steganography_image"
    description = (
        "PNG LSB 隐写检测 + 字节流提取 (单通道 + RGB 4 参数化; "
        "detect/extract/extract_bytes 3 mode; 替代 lsb_detect + lsb_extract + lsb_bytes_extract)"
    )

    default_timeout = 30.0

    def __init__(
        self,
        mode: str = "detect",
        preset: str | None = None,
        channels: str = "rgb",
        bit: int = 0,
        scan_order: str = "row",
        byte_bit_order: str = "msb",
        text_min_len: int = 20,
        entropy_threshold: float = 5.0,
        unique_threshold: int = 200,
    ):
        """工厂参数 (per spec §3.2 工厂参数).

        Args:
            mode: detect/extract/extract_bytes (默认 detect)
            preset: None/all/np (默认 None = auto-run 智能 12 组合 + entropy)
            channels/bit/scan_order/byte_bit_order: 4 参数
            text_min_len/entropy_threshold/unique_threshold: 检测阈值
        """
        self._action = LSBToolAction(
            mode=mode,
            preset=preset,
            channels=channels,
            bit=bit,
            scan_order=scan_order,
            byte_bit_order=byte_bit_order,
            text_min_len=text_min_len,
            entropy_threshold=entropy_threshold,
            unique_threshold=unique_threshold,
        )

    def run(self, file_path: str) -> ToolResult:
        """调 LSBToolAction 把 SP 装进 ToolResult.

        Args:
            file_path: PNG/JPG/BMP 图片路径

        Returns:
            ToolResult with suspicious_points list[SuspiciousPoint]
        """
        start = time.time()

        action_result = self._action.run({"file_path": file_path})
        duration_ms = int((time.time() - start) * 1000)

        exit_code = 0 if action_result.success else 1
        stdout = action_result.message or ""
        stderr = "" if action_result.success else (action_result.message or "")

        # 把 action_result.data["suspicious_points"] (dict 列表) 还原成 SuspiciousPoint
        suspicious: list[SuspiciousPoint] = []
        for sp_data in action_result.data.get("suspicious_points", []):
            suspicious.append(SuspiciousPoint(
                id="",
                tool_name=self.name,
                file_path=file_path,
                category=sp_data["category"],
                offset=None,
                matched_pattern=sp_data["matched_pattern"],
                severity=sp_data["severity"],
                suggested_action=sp_data.get("context", {}).get("suggested_action", "")
                if isinstance(sp_data.get("context"), dict)
                else "",
                context=str(sp_data.get("context", "")) if sp_data.get("context") else "",
            ))

        return ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )