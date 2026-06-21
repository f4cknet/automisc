"""内容意图检测器 — v0.5-decoder-friendly-hint

**职责**: 用户 paste 文本到 input 区时, 检测内容类型, 推荐对应 decoder.
GUI 集成点: ``InputOutputView.paste_clipboard()`` 末尾追加 hint 行.

**vs extract_base_candidate 区别**:
- ``extract_base_candidate``: 抽**候选文本** (给 decoder 跑) - 关注"取哪段"
- ``detect_input_intent``: 检**内容类型** (给用户提示) - 关注"推荐哪个 decoder"

**设计**:
- specificity 优先 (Ook! > BF > base64 > base32 > hex > binary > caesar)
- caesar 优先级最低 (全大写易误判, 仅 1-6 不命中时才建议)
- 返回 DetectionResult dataclass 含 decoder_name + display + kind + reason

**v0.5-decoder-friendly-hint 触发**: Owner 实战 2026-06-20 21:25 paste Ook! (2289 chars)
误点 BrainFuck decoder → output 全 \\x00. 加 hint 后用户能看提示直接选对.

**使用**:
```python
from automisc.core.decoders.content_detector import detect_input_intent

result = detect_input_intent(text)
if result:
    print(f"推荐 {result.display}: {result.reason}")
    # → 推荐 🦧 Ook! 解密: 含 Ook./Ook!/Ook? tokens
```
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionResult:
    """内容检测结果.

    Attributes:
        decoder_name: 推荐 decoder 的内部 name (e.g. "ook", "brainfuck", "hex-ascii")
        display: GUI 显示名 (e.g. "🦧 Ook! 解密")
        kind: 内容类型 (用户友好, e.g. "Ook! 代码", "BrainFuck 代码", "hex 串")
        reason: 检测原因 (简短, e.g. "含 Ook./Ook!/Ook? tokens")
    """

    decoder_name: str
    display: str
    kind: str
    reason: str


# GUI log 装饰行 — 检测前先剔除 (避免把 log 行误判成内容)
#   e.g. "[stderr] noop" / "=== Decoder: brainfuck ===" / "exit_code: 0"
# 修: 分两阶段 — 先跳纯空行, 再跳 log 装饰行 (避免 \s*$ 把正常行也吃掉)
_GUI_LOG_LINE_RE = re.compile(r"^\s*(\[[^\]]+\]|={3,}|---)")


def _strip_gui_log_lines(text: str) -> str:
    """剔除 input 文本中的 GUI log 装饰行, 保留真正 paste 的内容.

    用法: 启发式 — 纯空行 / [xxx] / === / --- 开头的行视为 log 装饰跳过.
    """
    kept: list[str] = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue  # 纯空行
        if _GUI_LOG_LINE_RE.match(line):
            continue  # log 装饰行
        kept.append(line)
    return "\n".join(kept)


def detect_input_intent(text: str) -> DetectionResult | None:
    """检测 input 区文本类型, 返回推荐 decoder.

    规则 (按 specificity 排序, 先命中先返回):

    1. **Ook!**: 含 ``Ook.``/``Ook!``/``Ook?`` token ≥ 2 个 + 长度 ≥ 20
       → ``ook`` decoder
    2. **BrainFuck**: 字符全在 BF 字符集 ``[+\\-<>\\[\\]., \\t]`` + 长度 ≥ 12
       + 含 ``[`` 或 ``]`` (BF 循环必要)
       → ``brainfuck`` decoder
    3. **base64**: 含 base64 特征字符 ``+/`` 或 行尾 ``=`` + 字符集合法
       + 长度 ≥ 16
       → ``base64`` decoder
    4. **base32**: 全字符集 ``[A-Z2-7= \\n\\r\\t]`` + 行尾 ``=`` + 长度 ≥ 8
       → ``base32`` decoder
    5. **hex**: 全 hex 字符 ``[0-9a-fA-F]`` + 偶数长度 + ≥ 8
       → ``hex-ascii`` decoder
    6. **binary**: 全 binary 字符 ``[01 \\n\\r\\t]`` + 长度 ≥ 8 且是 8 倍数
       → ``bin-ascii`` decoder
    7. **caesar**: 全大写字母 ``[A-Z]+`` + 长度 4-30 (易误判, 仅前 6 不命中时)
       → ``caesar`` decoder

    Args:
        text: input 区原始文本 (可能含 paste 的整段 / GUI log 装饰行)

    Returns:
        ``DetectionResult`` 或 ``None`` (空 / 太短 / 不符合任何规则)
    """
    if not text or not text.strip():
        return None

    # 1. 先剥 GUI log 行 (heuristic)
    stripped = _strip_gui_log_lines(text).strip()
    if not stripped:
        return None

    # 短文本门槛 (避免空 paste / 单字符)
    if len(stripped) < 4:
        return None

    # 2. Ook! — 最特异性 (token 必须成对, 至少 1 对 → 2 个 token)
    ook_tokens = re.findall(r"Ook[.!?]", stripped)
    if len(ook_tokens) >= 2 and len(stripped) >= 20:
        return DetectionResult(
            decoder_name="ook",
            display="🦧 Ook! 解密",
            kind="Ook! 代码",
            reason=f"含 {len(ook_tokens)} 个 Ook./Ook!/Ook? tokens",
        )

    # 3. BrainFuck — 必须有循环 ([ 或 ])
    if (
        len(stripped) >= 12
        and re.fullmatch(r"[+\-<>[\]., \t\n\r]+", stripped)
        and ("[" in stripped or "]" in stripped)
    ):
        return DetectionResult(
            decoder_name="brainfuck",
            display="🧠 BrainFuck 解密",
            kind="BrainFuck 代码",
            reason="全 BF 字符集 + 含 [ 或 ] 循环指令",
        )

    # 4. base64 — 含 +/ 或 行尾 = + 字符集合法 + 长度 ≥ 16
    if len(stripped) >= 16:
        has_base64_mid = bool(re.search(r"[+/]", stripped))
        has_base64_pad = stripped.rstrip().endswith("=")
        all_base64_chars = bool(
            re.fullmatch(r"[0-9a-zA-Z+/= \n\r\t]+", stripped)
        )
        # 排除明显的 URL / 注释行
        not_url_or_comment = not stripped.startswith(("http://", "https://", "//", "#"))
        if (has_base64_mid or has_base64_pad) and all_base64_chars and not_url_or_comment:
            return DetectionResult(
                decoder_name="base64",
                display="🔢 Base64",
                kind="base64 串",
                reason=(
                    "含 base64 特征字符 +"
                    if has_base64_mid
                    else "行尾有 = padding"
                ),
            )

    # 5. base32 — 全字符集 + 行尾 = + 长度 ≥ 8
    # 字符集放宽到 A-Z + 0-9 (Python base64.b32encode 实际输出含 0/1/8/9,
    # 严格 [A-Z2-7] 不够 — 实战 base32 串是 base64.b32encode(b"Hello World") 等输出)
    if (
        len(stripped) >= 8
        and re.fullmatch(r"[A-Z0-9= \n\r\t]+", stripped)
        and stripped.rstrip().endswith("=")
    ):
        return DetectionResult(
            decoder_name="base32",
            display="🔢 Base32",
            kind="base32 串",
            reason="全 A-Z 0-9 字符集 + 行尾 = padding",
        )

    # 6. binary — 先于 hex (全 01 是 hex 子集, binary 更 specific, 必须优先)
    compact = stripped.replace(" ", "").replace("\n", "").replace("\t", "").replace("\r", "")
    if (
        len(compact) >= 8
        and len(compact) % 8 == 0
        and re.fullmatch(r"[01]+", compact)
    ):
        return DetectionResult(
            decoder_name="bin-ascii",
            display="💻 2 进制转文本",
            kind="binary 串",
            reason=f"全 01 字符 + 长度 {len(compact)} 是 8 倍数",
        )

    # 7. hex — 全 hex 字符 + 偶数长度 + ≥ 8
    if (
        len(compact) >= 8
        and len(compact) % 2 == 0
        and re.fullmatch(r"[0-9a-fA-F]+", compact)
    ):
        return DetectionResult(
            decoder_name="hex-ascii",
            display="🔢 16 进制转文本",
            kind="hex 串",
            reason=f"全 hex 字符 ({len(compact)} chars)",
        )

    # 8. caesar — 全大写字母 + 长度 4-30 (低 confidence, 优先级最低)
    if (
        4 <= len(stripped) <= 30
        and re.fullmatch(r"[A-Z]+", stripped.replace(" ", ""))
        and not stripped.endswith("=")
    ):
        return DetectionResult(
            decoder_name="caesar",
            display="🔐 凯撒解密",
            kind="大写字母密文",
            reason=f"全大写字母 ({len(stripped)} chars, 可能凯撒/ROT13 密文)",
        )

    return None


__all__ = ["DetectionResult", "detect_input_intent"]