"""core.utils package (v0.5+ 通用工具).

独立于 actions/encoders/decoders 的纯函数工具.
"""
from automisc.core.utils.rule_scanner import (
    TextMatch,
    classify_text,
    has_any_suspicious,
    max_severity,
)

__all__ = ["TextMatch", "classify_text", "has_any_suspicious", "max_severity"]
