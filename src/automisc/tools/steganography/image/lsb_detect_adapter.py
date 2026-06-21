"""lsb_detect adapter (per tools.md §3.5 + v0.5-lsb-detector spec)

**lsb_detect** —— auto-run readonly 智能 LSB 检测 (替代 zsteg auto-run 位)

**触发**: v0.5-train-010-channel-lsb-anomaly.md — N=NP 大图副本实战, zsteg 漏 G 通道 LSB 单通道

**核心约束 (per AGENTS.md §1 铁律 7)**:
- **不写文件** (auto-run 纯探测, 字节流只进 SP.matched_pattern 截断 200 字符)
- **不触发下一步** (不调 lsb_bytes_extract / foremost / binwalk_extract 等操作类)
- **不雕不修不爆**

**需求 1** (per spec §2.1):
- RGB 3 通道 (Q2=A, 不含 alpha)
- 6 排列 × 2 scan = 12 组合
- text 判定 (printable ASCII 32-126) → sev=5
- 文件头双机制 (hex magic 主 + `file` 命令辅) → sev=5

**需求 2** (per spec §2.2):
- R/G/B 各自完整 8 bit 字节流
- entropy + unique count 跨通道比较
- 异常 → sev=4 (per Owner "没有绝对性")

**跟 zsteg 关系**: 替代 zsteg 在 FIND_SUSPICIOUS_PICTURE_TOOLS 中的位置
(Q1=A 拍板, 仍 6 tools 不变)

**跟 lsb_bytes_extract 关系**: 互补不替代
(lsb_bytes_extract 写文件 user-controlled 4 参数, lsb_detect readonly auto-run)
"""
from __future__ import annotations

from automisc.core.actions.lsb_detect import LSBDetectAction
from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.tools.base import ToolAdapter


@register_tool
class LsbDetectAdapter(ToolAdapter):
    """`lsb_detect` adapter —— auto-run readonly 智能 LSB 检测 (替代 zsteg).

    per spec §3.1 模块位置: tools/steganography/image/lsb_detect_adapter.py
    per spec §3.1 双注册: tools/__init__.py + steganography/image/ (namespace package)
    """

    name = "lsb_detect"
    category = "steganography_image"
    description = (
        "auto-run readonly 智能 LSB 检测 (RGB 3 通道 6 排列 × 2 scan = 12 组合 + "
        "3 通道 8 bit 概率检测, 替代 zsteg)"
    )

    # 默认 timeout: auto-run 池场景, 12 组合 + 3 通道 8 bit 算 entropy 约 150ms
    # 设宽到 30s 防止大图超时
    default_timeout = 30.0

    def __init__(
        self,
        entropy_threshold: float = 5.0,
        unique_threshold: int = 250,
        enable_channel_anomaly: bool = True,
    ):
        """工厂参数 (per spec §3.2 工厂参数).

        Args:
            entropy_threshold: 需求 2 entropy 阈值 (per spec §2.2 MVP 5.0)
            unique_threshold: 需求 2 unique count 阈值 (per spec §2.2 MVP 250/256)
            enable_channel_anomaly: 是否跑需求 2 (默认 True)
        """
        self._action = LSBDetectAction(
            entropy_threshold=entropy_threshold,
            unique_threshold=unique_threshold,
            enable_channel_anomaly=enable_channel_anomaly,
        )

    def run(self, file_path: str) -> ToolResult:
        """调 LSBDetectAction 把 SP 装进 ToolResult.

        Args:
            file_path: PNG/JPG/BMP 图片路径 (Q2=A RGB 3 通道)

        Returns:
            ToolResult with suspicious_points list[SuspiciousPoint]
        """
        import time
        start = time.time()

        # 调 core action (DAG Action 抽象, context dict 模式)
        action_result = self._action.run({"file_path": file_path})
        duration_ms = int((time.time() - start) * 1000)

        # exit_code: action.success 决定
        exit_code = 0 if action_result.success else 1
        stdout = action_result.message
        stderr = "" if action_result.success else action_result.message

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
