"""automisc 错误体系单测（v0.1.1 exceptions.py）"""
from __future__ import annotations

import pytest

from automisc.core.exceptions import (
    AutomiscError,
    FileNotAutomiscError,
    RegistryError,
    RoutingError,
    ToolNotFoundError,
    ToolOutputError,
    ToolRunError,
)


class TestAutomiscError:
    def test_inheritance(self):
        """所有子类继承 AutomiscError."""
        for cls in [RegistryError, RoutingError, ToolNotFoundError,
                    ToolRunError, ToolOutputError, FileNotAutomiscError]:
            assert issubclass(cls, AutomiscError)
            assert issubclass(cls, Exception)

    def test_message_only(self):
        e = AutomiscError("simple")
        assert str(e) == "AutomiscError: simple"
        assert e.message == "simple"
        assert e.context == {}

    def test_message_with_context(self):
        e = AutomiscError("failed", context={"tool": "strings", "file": "x.txt"})
        assert "AutomiscError" in str(e)
        assert "failed" in str(e)
        assert "tool=" in str(e)
        assert "file=" in str(e)
        assert "strings" in str(e)
        assert "x.txt" in str(e)

    def test_cause_chain(self):
        """raise ... from e 保留 __cause__."""
        try:
            raise ValueError("inner")
        except ValueError as e:
            outer = ToolRunError("outer")
            outer.__cause__ = e
            assert outer.__cause__ is e


class TestRegistryError:
    def test_raise(self):
        with pytest.raises(AutomiscError):  # 父类可捕获
            raise RegistryError("dup name", context={"name": "binwalk"})

    def test_caught_as_registry_error(self):
        with pytest.raises(RegistryError):
            raise RegistryError("dup name", context={"name": "binwalk"})


class TestToolNotFoundError:
    def test_raise(self):
        with pytest.raises(ToolNotFoundError) as excinfo:
            raise ToolNotFoundError("not found", context={"name": "x"})
        assert excinfo.value.context["name"] == "x"


class TestFileNotAutomiscError:
    def test_not_found_factory(self):
        e = FileNotAutomiscError.not_found("/tmp/foo")
        assert "not found" in str(e)
        assert e.context["path"] == "/tmp/foo"
        assert e.context["reason"] == "not_found"

    def test_not_readable_factory(self):
        e = FileNotAutomiscError.not_readable("/tmp/foo", reason="EACCES")
        assert e.context["reason"] == "EACCES"

    def test_too_large_factory(self):
        e = FileNotAutomiscError.too_large("/tmp/big", size=10_000_000, max_size=1_000_000)
        assert e.context["size"] == 10_000_000
        assert e.context["max_size"] == 1_000_000

    def test_caught_as_automisc_error(self):
        """GUI 层 try/except AutomiscError 可统一捕获文件错误."""
        with pytest.raises(AutomiscError):
            raise FileNotAutomiscError.not_found("/x")
