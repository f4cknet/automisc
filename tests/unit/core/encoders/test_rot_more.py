"""测试 core/encoders/classical.py 新增算法（per v0.5-base-rot-decoders PR1）

覆盖: ROT5 / ROT47 / ROT18
"""
from __future__ import annotations

from automisc.core.encoders.classical import (
    rot5,
    rot13,
    rot18,
    rot47,
)


# === ROT5 ===

def test_rot5_digits():
    """ROT5 仅作用于 digits 0-9"""
    assert rot5("0123456789") == "5678901234"


def test_rot5_letters_unchanged():
    """ROT5 不影响字母"""
    assert rot5("hello") == "hello"


def test_rot5_mixed():
    """ROT5 数字旋转 + 字母不变"""
    assert rot5("abc123XYZ") == "abc678XYZ"


def test_rot5_invertible():
    """ROT5 是自反的（ROT5(ROT5(x)) == x）"""
    assert rot5(rot5("0123456789")) == "0123456789"


# === ROT47 ===

def test_rot47_basic():
    """ROT47 作用于 ASCII 33-126 整段"""
    # '!' (33): (33-33+47) % 94 + 33 = 47 + 33 = 80 = 'P'
    assert rot47("!") == "P"
    # 'a' (97): (97-33+47) % 94 + 33 = 111 % 94 + 33 = 17 + 33 = 50 = '2'
    assert rot47("a") == "2"
    # '~' (126): (126-33+47) % 94 + 33 = 140 % 94 + 33 = 46 + 33 = 79 = 'O'
    assert rot47("~") == "O"


def test_rot47_letters():
    """ROT47 字母位移"""
    # h(104): (104-33+47) % 94 + 33 = 118 % 94 + 33 = 24 + 33 = 57 = '9'
    # e(101): (101-33+47) % 94 + 33 = 115 % 94 + 33 = 21 + 33 = 54 = '6'
    # l(108): (108-33+47) % 94 + 33 = 122 % 94 + 33 = 28 + 33 = 61 = '='
    # o(111): (111-33+47) % 94 + 33 = 125 % 94 + 33 = 31 + 33 = 64 = '@'
    assert rot47("hello") == "96==@"


def test_rot47_out_of_range_unchanged():
    """ROT47 不作用于 ASCII < 33 或 > 126"""
    # ' '(32) 不变
    assert rot47("a b") == "2 3"
    # 中文 (>126) 不变
    assert rot47("你好") == "你好"


def test_rot47_invertible():
    """ROT47 是自反的"""
    assert rot47(rot47("hello world!")) == "hello world!"


def test_rot47_chinese_unchanged():
    """ROT47 不影响中文（> 126）"""
    assert rot47("你好") == "你好"


def test_rot47_invertible():
    """ROT47 是自反的"""
    assert rot47(rot47("hello world!")) == "hello world!"


def test_rot47_chinese_unchanged():
    """ROT47 不影响中文（> 126）"""
    assert rot47("你好") == "你好"


# === ROT18 ===

def test_rot18_combines_rot5_and_rot13():
    """ROT18 = ROT13(字母) + ROT5(数字)"""
    # "abc" → "nop" (rot13), "123" → "678" (rot5)
    assert rot18("abc123") == "nop678"


def test_rot18_letters_only():
    """只有字母时 ROT18 = ROT13"""
    assert rot18("hello") == rot13("hello")


def test_rot18_digits_only():
    """只有数字时 ROT18 = ROT5"""
    assert rot18("12345") == rot5("12345")


def test_rot18_invertible():
    """ROT18 是自反的（应用两次回到原值）"""
    assert rot18(rot18("Hello123")) == "Hello123"


# === 回归 ===

def test_rot13_still_works():
    """回归：ROT13 仍正常工作"""
    assert rot13("hello") == "uryyb"
    assert rot13("uryyb") == "hello"
