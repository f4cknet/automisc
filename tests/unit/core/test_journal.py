"""Journal 单测（v0.1.1 core/journal.py）"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from automisc.core.journal import Journal, JournalEntry
from automisc.core.suspicious import SuspiciousPoint


def _sp(kind: str, severity: int, value: str = "test") -> SuspiciousPoint:
    return SuspiciousPoint(
        id="",
        tool_name="t",
        file_path="/x",
        category=kind,
        matched_pattern=value,
        severity=severity,
        suggested_action="",
    )


class TestJournalRecord:
    def test_record_creates_entry(self):
        j = Journal()
        e = j.record("strings", "/tmp/x", 0, [_sp("flag", 5, "flag{abc}")])
        assert isinstance(e, JournalEntry)
        assert e.tool_name == "strings"
        assert e.exit_code == 0
        assert len(e.suspicious_points) == 1
        assert j.entries().__len__() == 1

    def test_record_default_timestamp(self):
        j = Journal()
        before = datetime.now()
        e = j.record("t", "/x", 0, [])
        after = datetime.now()
        assert before <= e.timestamp <= after

    def test_record_custom_timestamp(self):
        j = Journal()
        ts = datetime(2026, 1, 1, 12, 0, 0)
        e = j.record("t", "/x", 0, [], timestamp=ts)
        assert e.timestamp == ts

    def test_record_with_error(self):
        j = Journal()
        e = j.record("t", "/x", 1, [], error="timeout")
        assert e.error == "timeout"

    def test_record_preserves_suspicious_list(self):
        """传入 list 应被 copy（外部修改不影响 entry）."""
        sps = [_sp("flag", 5)]
        j = Journal()
        j.record("t", "/x", 0, sps)
        sps.append(_sp("x", 1))  # 外部修改
        e = j.entries()[0]
        assert len(e.suspicious_points) == 1  # 不受影响


class TestJournalQuery:
    def test_entries_returns_copy(self):
        j = Journal()
        j.record("t", "/x", 0, [])
        e1 = j.entries()
        e1.clear()
        assert len(j.entries()) == 1

    def test_filter_by_tool(self):
        j = Journal()
        j.record("strings", "/x", 0, [_sp("flag", 5)])
        j.record("tshark", "/y", 0, [_sp("x", 3)])
        e = j.filter_by_tool("strings")
        assert len(e) == 1
        assert e[0].file_path == "/x"

    def test_filter_by_severity(self):
        j = Journal()
        j.record("t", "/x", 0, [_sp("a", 5), _sp("b", 2)])
        j.record("t", "/y", 0, [_sp("c", 1)])
        e = j.filter_by_severity(min_severity=3)
        assert len(e) == 1
        assert e[0].file_path == "/x"

    def test_suspicious_points_flattened(self):
        j = Journal()
        j.record("t1", "/x", 0, [_sp("a", 5), _sp("b", 3)])
        j.record("t2", "/y", 0, [_sp("c", 4)])
        sps = j.suspicious_points()
        assert len(sps) == 3

    def test_count_by_category(self):
        j = Journal()
        j.record("t", "/x", 0, [_sp("flag", 5), _sp("flag", 5), _sp("keyword", 3)])
        c = j.count_by_category()
        assert c == {"flag": 2, "keyword": 1}

    def test_count_by_tool(self):
        j = Journal()
        j.record("strings", "/x", 0, [])
        j.record("strings", "/y", 0, [])
        j.record("tshark", "/z", 0, [])
        c = j.count_by_tool()
        assert c == {"strings": 2, "tshark": 1}


class TestJournalPersistence:
    def test_flush_to_jsonl(self, tmp_path):
        j = Journal()
        j.record("strings", "/x", 0, [_sp("flag", 5, "flag{abc}")])
        out = tmp_path / "journal.jsonl"
        j.flush_to_jsonl(out)
        assert out.exists()
        # 读回
        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert d["tool_name"] == "strings"
        assert d["suspicious_points"][0]["matched_pattern"] == "flag{abc}"
        assert d["timestamp"]  # ISO format

    def test_flush_creates_parent_dir(self, tmp_path):
        j = Journal()
        j.record("t", "/x", 0, [])
        out = tmp_path / "subdir" / "deep" / "journal.jsonl"
        j.flush_to_jsonl(out)
        assert out.exists()


class TestJournalClear:
    def test_clear(self):
        j = Journal()
        j.record("t", "/x", 0, [])
        j.clear()
        assert len(j.entries()) == 0
