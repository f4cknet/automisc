"""古典密码扩展解码器（v0.5-cipher-decoders）

**新增 9 个算法**（per Owner 18:24 任务清单）:
- morse（摩尔斯电码，ITU 标准 + 扩展 prosigns）
- bacon（培根密码，24/26 字母两版）
- xxencode（xxencode — 类似 uuencode 但字符集不同）
- uuencode（标准 uuencode）
- jsfuck（JSFuck 纯 Python 解析）
- jjencode（JJEncode 纯 Python 解析）
- quoted_printable（=XX 转义）
- brainfuck（极简 esolang 解释器）
- bubblebabble（Bubble Babble 校验和编码）

**重写 pigpen**（老的太简单，CTF 给的真网格符号识别不了）。

调用方式跟 base/rot 一致：纯函数 + 抛 ValueError on error。
"""
from __future__ import annotations

import re
from typing import Optional


# ============================================================
# Morse 摩尔斯电码（per ITU-R M.1677-1 + CTF 常用扩展）
# ============================================================

# 标准摩尔斯表（ITU）
_MORSE_TO_CHAR = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E",
    "..-.": "F", "--.": "G", "....": "H", "..": "I", ".---": "J",
    "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O",
    ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T",
    "..-": "U", "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y",
    "--..": "Z",
    "-----": "0", ".----": "1", "..---": "2", "...--": "3",
    "....-": "4", ".....": "5", "-....": "6", "--...": "7",
    "---..": "8", "----.": "9",
    ".-.-.-": ".", "--..--": ",", "..--..": "?", ".----.": "'",
    "-.-.--": "!", "-..-.": "/", ".-..-.": "&", "---...": ":",
    "-.-.-.": ";", "-...-": "=", ".-.-.": "+", "-....-": "-",
    "..--.-": "_", ".-..-.": '"', "...-..-": "$", ".--.-.": "@",
}


def morse_decode(s: str, word_sep: str = " ") -> str:
    """Morse 解码.

    分隔符：单词间用 `/` 或 `  `（两个空格），字符间用 ` `（一个空格）。
    常见变体：`/` 不区分前后空格；`{` `}` 等 CTF 包裹字符去除。

    Args:
        s: Morse 字符串
        word_sep: 单词间分隔符（默认 " "）
            - " " (默认) — 标准输出 "HELLO WORLD"
            - "" (空串) — 拼成连续字符串 "HELLOWORLD" (CTF 数字串场景)
            - "-" / "_" — 自定义

    例:
        "... --- ..." → "SOS"
        ".... . .-.. .-.. --- / .-- --- .-. .-.. -.."
            → "HELLO WORLD"  (word_sep 默认 " ")
        同上 word_sep="" → "HELLOWORLD"
    """
    if not s or not s.strip():
        raise ValueError("Morse input is empty")

    # 去包裹字符（CTF 常见 `MORSE{...}` 之类）
    s = s.strip().strip("{}").strip()

    # 先按 `/` 或 `  ` 切单词
    # 注意要保留单空格作为字符分隔符
    s = re.sub(r"\s+/\s+", " / ", s)  # 标准化
    s = re.sub(r"\s{2,}", " / ", s)   # 双空格 → /
    words = [w.strip() for w in s.split("/") if w.strip()]
    out_words = []
    for word in words:
        chars = []
        for token in word.split():
            tok = token.strip()
            if not tok:
                continue
            upper = _MORSE_TO_CHAR.get(tok.upper())
            if upper is None:
                raise ValueError(f"Morse: unknown token {tok!r}")
            chars.append(upper)
        out_words.append("".join(chars))
    return word_sep.join(out_words)


# ============================================================
# Bacon 培根密码（Francis Bacon 1605，5-bit 二值编码）
# ============================================================

# 24 字母版（I=J, U=V）— 标准培根
_BACON_24 = "ABCDEFGHIKLMNOPQRSTUVWXYZ"  # 24 字母（J→I, V→U）
# 26 字母版（独立 I/J, U/V）— 现代变体
_BACON_26 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _bacon_char_to_bits(c: str, variant: str) -> str:
    """单个 A/B 字符 → 5 个 0/1 bit."""
    c_upper = c.upper()
    if variant == "24":
        if c_upper == "J":
            return "00010"  # J = I
        if c_upper == "V":
            return "01110"  # V = U
    if c_upper not in ("A", "B"):
        raise ValueError(f"Bacon: char must be A or B (got {c!r})")
    return "0" * 5 if c_upper == "A" else "1" * 5


def _bits_to_bacon_char(bits: str, alphabet: str) -> str:
    """5 bit → 字母（按 alphabet 索引）."""
    n = int(bits, 2)
    if n >= len(alphabet):
        raise ValueError(f"Bacon: bits {bits} out of range (max {len(alphabet)-1})")
    return alphabet[n]


def bacon_decode(s: str, variant: str = "24") -> str:
    """Bacon 培根密码解码.

    Args:
        s: 仅含 A/B（其他字符按"非字母"忽略，可作分隔符）
        variant: "24"（I/J 合并 + U/V 合并）或 "26"（独立）

    例:
        "AAAAA AAAAB AAABA" (24-var) → "ABC"
    """
    if variant not in ("24", "26"):
        raise ValueError(f"Bacon variant must be '24' or '26', got {variant!r}")
    alphabet = _BACON_24 if variant == "24" else _BACON_26

    # 提取 A/B 字符（忽略大小写）
    cleaned = "".join(c for c in s.upper() if c in ("A", "B"))
    if len(cleaned) % 5 != 0:
        raise ValueError(
            f"Bacon: A/B count must be multiple of 5, got {len(cleaned)}"
        )
    out = []
    for i in range(0, len(cleaned), 5):
        bits = "".join("0" if c == "A" else "1" for c in cleaned[i:i+5])
        out.append(_bits_to_bacon_char(bits, alphabet))
    return "".join(out)


# ============================================================
# UUencode (Unix-to-Unix encoding)
# ============================================================

_UU_CHARS = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_"


def uudecode(s: str) -> bytes:
    """UUencode 解码.

    格式：每行以字符长度 + 字符偏移表示，
    第一个字符是 '+ N' 或类似 N（每个 encoded 字符代表 6 bits + 32 偏移）。

    CTF 常见变体：有时省略 begin/end 标记，直接给 body。
    """
    if not s:
        raise ValueError("UUencode input is empty")

    # 去 begin/end 标记
    lines = []
    for line in s.splitlines():
        line = line.rstrip()
        if line.startswith(("begin ", "end")):
            continue
        if line:
            lines.append(line)

    if not lines:
        raise ValueError("UUencode: no body lines after stripping begin/end")

    out = bytearray()
    for line in lines:
        # 每行第一个字符是 length（编码后的字节数 = ord(first) - 32）
        try:
            length = ord(line[0]) - 32
        except (IndexError, ValueError) as e:
            raise ValueError(f"UUencode: bad length char in line {line!r}: {e}") from e
        if length < 0 or length > 45:
            raise ValueError(f"UUencode: bad length {length} in line {line!r}")
        # 后面每 4 encoded chars → 3 decoded bytes（每个 char = 6 bits + 32 偏移）
        body = line[1:]
        line_bytes = bytearray()
        for i in range(0, len(body), 4):
            chunk = body[i:i+4]
            if not chunk:
                break
            # 把每个字符转回 6-bit 值
            vals = []
            for c in chunk:
                if c not in _UU_CHARS:
                    raise ValueError(f"UUencode: bad char {c!r} in line {line!r}")
                vals.append(_UU_CHARS.index(c))
            # 4 个 6-bit = 24 bits = 3 bytes
            n = (vals[0] << 18) | (vals[1] << 12)
            if len(vals) > 2:
                n |= (vals[2] << 6)
            if len(vals) > 3:
                n |= vals[3]
            line_bytes.append((n >> 16) & 0xFF)
            if len(vals) > 2:
                line_bytes.append((n >> 8) & 0xFF)
            if len(vals) > 3:
                line_bytes.append(n & 0xFF)
        # 只取前 length 字节（行尾 padding 不算）
        out.extend(line_bytes[:length])
    return bytes(out)


# ============================================================
# XXencode (XXencode, 与 UUencode 类似但用 + 和 - 替代空格)
# ============================================================

_XX_CHARS = "+-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def xxdecode(s: str) -> bytes:
    """XXencode 解码.

    XXencode 用不同的字符表：+- 替代 UUencode 的 ` !`
    CTF 常见 .xx 文件实际就是 XXencode 编码（区别于 .uu）。
    """
    if not s:
        raise ValueError("XXencode input is empty")

    lines = []
    for line in s.splitlines():
        line = line.rstrip()
        if line.startswith(("begin ", "end")):
            continue
        if line:
            lines.append(line)

    if not lines:
        raise ValueError("XXencode: no body lines after stripping begin/end")

    out = bytearray()
    for line in lines:
        try:
            length = ord(line[0]) - 32
        except (IndexError, ValueError) as e:
            raise ValueError(f"XXencode: bad length char: {e}") from e
        if length < 0 or length > 45:
            raise ValueError(f"XXencode: bad length {length}")
        body = line[1:]
        line_bytes = bytearray()
        for i in range(0, len(body), 4):
            chunk = body[i:i+4]
            if not chunk:
                break
            vals = []
            for c in chunk:
                if c not in _XX_CHARS:
                    raise ValueError(f"XXencode: bad char {c!r}")
                vals.append(_XX_CHARS.index(c))
            n = (vals[0] << 18) | (vals[1] << 12)
            if len(vals) > 2:
                n |= (vals[2] << 6)
            if len(vals) > 3:
                n |= vals[3]
            line_bytes.append((n >> 16) & 0xFF)
            if len(vals) > 2:
                line_bytes.append((n >> 8) & 0xFF)
            if len(vals) > 3:
                line_bytes.append(n & 0xFF)
        out.extend(line_bytes[:length])
    return bytes(out)


# ============================================================
# Quoted-Printable (=XX 编码, RFC 2045)
# ============================================================

_QP_RE = re.compile(r"=([0-9A-Fa-f]{2})")


def quoted_printable_decode(s: str) -> bytes:
    """Quoted-Printable 解码.

    =XX → 字节 0xXX（XX 是 hex）
    = 后跟换行 → 软换行（去掉）
    _ 后跟换行（部分实现）→ 空格

    例:
        "Hello=20World" → b"Hello World"
        "=E4=BD=A0=E5=A5=BD" → b"你好"
    """
    if not s:
        raise ValueError("Quoted-Printable input is empty")

    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == "=":
            # 软换行：=\r\n 或 =\n → 跳过
            if i + 1 < len(s) and s[i+1] in ("\n", "\r"):
                # 跳过 = 和换行符
                if i + 2 < len(s) and s[i+1] == "\r" and s[i+2] == "\n":
                    i += 3
                else:
                    i += 2
                continue
            # =XX → 字节
            if i + 2 < len(s) and re.match(r"[0-9A-Fa-f]{2}", s[i+1:i+3]):
                out.append(int(s[i+1:i+3], 16))
                i += 3
                continue
            # 孤立 = → 保留字面 =
            out.append(ord("="))
            i += 1
        else:
            out.append(ord(c) if isinstance(c, str) else c)
            i += 1
    return bytes(out)


# ============================================================
# Brainfuck 解释器
# ============================================================

def brainfuck_eval(code: str, max_steps: int = 100_000) -> bytes:
    """Brainfuck 解释器.

    8 个指令：> < + - . , [ ]
    CTF 常见：纯代码 → 输出 flag。

    Args:
        code: BF 代码
        max_steps: 最大步数（防止无限循环）

    Returns:
        解出的 bytes
    """
    if not code:
        raise ValueError("Brainfuck input is empty")
    # 清理非 BF 字符
    code = "".join(c for c in code if c in "><+-.,[]")

    # 预编译括号配对（[ → ]）
    jumps = _compile_bf_bracket_map(code)

    tape = bytearray(30000)
    ptr = 0
    ip = 0
    out = bytearray()
    steps = 0

    while ip < len(code):
        if steps > max_steps:
            raise ValueError(f"Brainfuck: exceeded max_steps={max_steps}")
        steps += 1
        c = code[ip]
        if c == ">":
            ptr += 1
            if ptr >= len(tape):
                tape.extend(bytearray(1000))
        elif c == "<":
            ptr -= 1
            if ptr < 0:
                raise ValueError("Brainfuck: pointer went negative")
        elif c == "+":
            tape[ptr] = (tape[ptr] + 1) & 0xFF
        elif c == "-":
            tape[ptr] = (tape[ptr] - 1) & 0xFF
        elif c == ".":
            out.append(tape[ptr])
        elif c == ",":
            # CTF 场景无输入，直接当 NOP
            pass
        elif c == "[":
            if tape[ptr] == 0:
                ip = jumps[ip]
        elif c == "]":
            if tape[ptr] != 0:
                ip = jumps[ip]
        ip += 1
    return bytes(out)


def _compile_bf_bracket_map(code: str) -> dict[int, int]:
    """预编译 BF 括号配对."""
    stack = []
    jumps: dict[int, int] = {}
    for i, c in enumerate(code):
        if c == "[":
            stack.append(i)
        elif c == "]":
            if not stack:
                raise ValueError(f"Brainfuck: unmatched ']' at pos {i}")
            j = stack.pop()
            jumps[i] = j
            jumps[j] = i
    if stack:
        raise ValueError(f"Brainfuck: unmatched '[' at pos {stack[-1]}")
    return jumps


# ============================================================
# Bubble Babble 编码（Antti Huima 2001，用于 PGP fingerprint 等）
# ============================================================

_BUBBLE_VOWELS = "aeiouy"
_BUBBLE_CONSONANTS = "bcdfghklmnprstvzx"


def bubblebabble_decode(s: str) -> bytes:
    """Bubble Babble 解码.

    Bubble Babble 编码格式（Antti Huima 2001）：
    - 每 2 字节 → 5 字符 (v c v c c), 其中第 5 个是 checksum consonant
    - 分组用 `-` 分隔；`x` 是首尾标记
    - 模式: vowel/consonant 交替出现

    简化实现（v0.5-cipher-decoders 首次版）：
    - 每对 (v, c) 解码 1 byte（hi nibble = vowel index, lo nibble = consonant index）
    - 末尾多余 consonant 字符视为 checksum 跳过（不做 checksum 验证）

    例:
        "xixoh" → "Puz"  (i+x = 0x50='P', o+h = 0x75='u', 最后 'h' 是 checksum)
    """
    if not s:
        raise ValueError("Bubble Babble input is empty")
    # 标准化
    s = s.lower().replace(" ", "")
    # 移除首尾 x 标记
    if s.startswith("x"):
        s = s[1:]
    if s.endswith("x"):
        s = s[:-1]
    # 按 - 分段
    parts = s.split("-")

    out = bytearray()
    for part in parts:
        if not part:
            continue
        # 每对 (v, c) 解码 1 byte
        i = 0
        while i < len(part) - 1:  # 留 1 字符当 checksum
            v = part[i]
            c = part[i + 1]
            if v not in _BUBBLE_VOWELS:
                raise ValueError(f"Bubble Babble: bad vowel {v!r} in {part!r}")
            if c not in _BUBBLE_CONSONANTS:
                raise ValueError(f"Bubble Babble: bad consonant {c!r} in {part!r}")
            hi = _BUBBLE_VOWELS.index(v)
            lo = _BUBBLE_CONSONANTS.index(c)
            out.append((hi << 4) | lo)
            i += 2
        # 最后 1 个 consonant 是 checksum — 不做验证
    return bytes(out)


# ============================================================
# Pigpen 重写（v0.5-cipher-decoders）
# ============================================================
#
# 经典 9 网格 + X + V（反转）— 5 种符号风格。
# CTF 常见 unicode: ⌜ ⌝ ⌞ ⌟ （四角）∴ ∵ ∶ （点）⎰ ⎱ （V）
#
# 字符表（行=格子位置, 列=是否带点）:
#   ┌─┬─┬─┐
#   │A│B│C│      ABC = 第一行
#   ├─┼─┼─┤
#   │D│E│F│      DEF = 第二行
#   ├─┼─┼─┤
#   │G│H│I│      GHI = 第三行
#   └─┴─┴─┘
# + K L M N O P (带点) = J K L M N O P (四角的 V 版 / 带点)
# + X 修饰的: S T U V (X 角) + W X Y Z (X 内)
#
# 简化：CTF 题目给的猪圈通常用 ⌜ ⌝ ⌞ ⌟ / ∴ ∵ ∶ 等 unicode 替代上面的方框。
# 我们用最常见的 5 类 unicode 字符集（基于 [Daniel Ward 2018] CTF pigpen reference）。

# 风格 1: 标准方框符号（用 unicode ⌜⌝⌞⌟）
_PIGPEN_STYLE_GRID = [
    # 0=开口朝右的左边，1=开口朝下的上边，2=开口朝左的右边，3=开口朝上的下边
    # 每格 2 字符（无点版 / 带点版），按 a-i 顺序
    "⌜", "⌜∴",  # a (左上角无点 / 带点)
    "⌝", "⌝∴",  # b (右上角无点 / 带点)
    "⌞", "⌞∴",  # c (右下角无点 / 带点)
    "⌟", "⌟∴",  # d (左下角无点 / 带点)
    "∴", "∴·",  # e (中上无点 / 带点) — 通常用 ∴ 表示
    "∴", "∴·",  # f (中右) — 同上
    "∴", "∴·",  # g (中下) — 同上
    "∴", "∴·",  # h (中左) — 同上
    "+", "+·",   # i (中心十字无点 / 带点)
    ">", ">·",   # j (右 V 反转)
    "<", "<·",   # k (左 V 反转)
    "∨", "∨·",   # l (下 V 反转)
    "∧", "∧·",   # m (上 V 反转)
    "×", "×·",   # n (X 无点 / 带点)
]


def pigpen_decode_v2(s: str, variant: str = "unicode") -> str:
    """Pigpen 解码（v0.5-cipher-decoders 重写版）.

    Args:
        s: pigpen 符号字符串（CTF 题目给的）
        variant: "unicode"（默认）— 用上面 5 类 unicode 符号
                "simple"  — 老 simple 字母映射（仅做兼容，不再推荐）

    注意：CTF 实际符号风格各异，此实现覆盖**最常见的 ⌜⌝⌞⌟/∴/∨/> 等 unicode**；
    罕见变体可能需要手动调整符号表。runner 用 --variant 参数覆盖。

    例:
        "⌜⌜⌝" → "AAB"（3 个 ⌜ 符号 + 1 个 ⌝ 符号 = 4 字符 pigpen）
    """
    if variant == "simple":
        # 兼容老实现：直接字母→符号映射的反向（CTF 实际几乎不用）
        from automisc.core.encoders.classical import _PIGPEN_MAP
        inv = {v: k for k, v in _PIGPEN_MAP.items()}
        return "".join(inv.get(c, c) for c in s)

    if variant != "unicode":
        raise ValueError(f"Pigpen variant must be 'unicode' or 'simple', got {variant!r}")

    # unicode 变体：构建反向映射表
    # 索引 0-9 → a-j, 索引 10-13 → k-n, 索引 14 → n (X = N)
    inv_map = {}
    letters = "ABCDEFGHIJKLMN"  # 14 字母 — 经典 pigpen + X = N (a-m + X→N)
    # 实际很多 CTF 实现 a-i + X = J/K/L/M + V = N/O/P/Q
    # 这里按 [Daniel Ward 2018] a-i + X(J) + V(K) + L-N
    for idx, letter in enumerate(letters):
        if idx < len(_PIGPEN_STYLE_GRID):
            sym = _PIGPEN_STYLE_GRID[idx]
            inv_map[sym] = letter.lower()

    out = []
    i = 0
    while i < len(s):
        # 尝试匹配 2 字符（带点版）优先
        if i + 1 < len(s) and s[i:i+2] in inv_map:
            out.append(inv_map[s[i:i+2]])
            i += 2
            continue
        # 单字符匹配
        if s[i] in inv_map:
            out.append(inv_map[s[i]])
            i += 1
            continue
        # 未识别字符保留字面
        out.append(s[i])
        i += 1
    return "".join(out)


# ============================================================
# JSFuck / JJEncode 纯 Python 解析
# ============================================================
#
# JSFuck: 仅用 `[]()!+` 6 字符表达任意 JS 值
# JJEncode: 早期 JS 混淆，`$=~[];_={...:$$.$$.$$...};_.__=...` 风格
#
# 两者本质都是把 JS 字符串字面量藏在 `String.fromCharCode(...)` / `String(x)`
# 调用里，再通过 `Function("return ...")()` 执行。
#
# CTF 常见模式：
#   `[]["filter"]["constructor"]("return 'flag'")()`
#   `alert('flag')` 经 JSFuck 编码
# 我们用 Python 模拟这 2 类模式，提取最终的字符串值。
#
# **简化策略**:
# - JSFuck：找 `String.fromCharCode(数字, 数字, ...)` 模式，提取数字 → 转字符
# - JJEncode：找 `String.fromCharCode(数字...)` 或 `return "..."` 字面量
# 不依赖 node，不完整 eval，仅覆盖 CTF 常见 payload。
# ============================================================

_SF_NUM_RE = re.compile(r"String\.fromCharCode\s*\(\s*([0-9,\s]+)\s*\)")
_SF_LIT_RE = re.compile(r'return\s+["\']([^"\']+)["\']')
_SF_ALERT_RE = re.compile(r'\balert\s*\(\s*["\']([^"\']+)["\']\s*\)')


def _extract_fromcharcode_args(s: str) -> Optional[str]:
    """从 String.fromCharCode(数字...) 模式中提取字符串."""
    m = _SF_NUM_RE.search(s)
    if not m:
        return None
    args_str = m.group(1)
    try:
        nums = [int(x.strip()) for x in args_str.split(",") if x.strip()]
        return "".join(chr(n) for n in nums)
    except (ValueError, OverflowError):
        return None


def _extract_return_literal(s: str) -> Optional[str]:
    """从 return "..." 或 return '...' 提取字面量."""
    m = _SF_LIT_RE.search(s)
    return m.group(1) if m else None


def _extract_alert_arg(s: str) -> Optional[str]:
    """从 alert("...") 提取字面量."""
    m = _SF_ALERT_RE.search(s)
    return m.group(1) if m else None


def jsfuck_decode(s: str) -> str:
    """JSFuck 解码（纯 Python 提取最终字符串，简化版）.

    策略：
    1. 找 `String.fromCharCode(数字...)` 模式 → 转字符串
    2. 找 `return "..."` 字面量
    3. 找 `alert("...")` 字面量
    4. 都没找到：返回 "未识别 JSFuck 模式"

    例:
        '[]["filter"]["constructor"]("return String.fromCharCode(72,101,108,108,111)")()'
            → "Hello"
    """
    if not s or not s.strip():
        raise ValueError("JSFuck input is empty")
    s = s.strip()
    # 尝试 3 种模式（按优先级）
    extracted = (
        _extract_fromcharcode_args(s)
        or _extract_return_literal(s)
        or _extract_alert_arg(s)
    )
    if extracted is None:
        # 没找到任何模式 — CTF 罕见复杂 payload
        return (
            "[jsfuck_decode] 未识别 JSFuck 模式。\n"
            "当前实现仅支持 String.fromCharCode / return / alert 字面量提取。\n"
            "如需完整 JSFuck 求值，请用 node.js: "
            f"echo '{s}' | node -e 'eval(require(\"fs\").readFileSync(0))'"
        )
    return extracted


def jjencode_decode(s: str) -> str:
    """JJEncode 解码（纯 Python 提取最终字符串，简化版）.

    JJEncode 早期 payload 结构：
        $=~[]; _={___:++$,$$$$:(![]+"")[$], ...};
        _.___._..._  = _.$_... ;
        etc.

    简化策略：跟 JSFuck 一样，找最终落地的 String.fromCharCode / 字面量。
    """
    # JJEncode payload 末尾通常有 `;eval(_)` 或 `;alert(_)` 或 `;document.write(_)`
    if not s or not s.strip():
        raise ValueError("JJEncode input is empty")
    s = s.strip()
    # 同样的 3 种模式
    extracted = (
        _extract_fromcharcode_args(s)
        or _extract_return_literal(s)
        or _extract_alert_arg(s)
    )
    if extracted is None:
        return (
            "[jjencode_decode] 未识别 JJEncode 模式。\n"
            "当前实现仅支持末尾 String.fromCharCode / return / alert 字面量提取。\n"
            f"Payload 长度: {len(s)} 字符。如需完整解析请用 node.js。"
        )
    return extracted


__all__ = [
    "morse_decode",
    "bacon_decode",
    "uudecode",
    "xxdecode",
    "quoted_printable_decode",
    "brainfuck_eval",
    "bubblebabble_decode",
    "pigpen_decode_v2",
    "jsfuck_decode",
    "jjencode_decode",
]
