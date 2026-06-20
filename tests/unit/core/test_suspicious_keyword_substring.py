"""测试 core/suspicious.py + gui/journal_panel.py — keyword 子串匹配 + severity 5 + GUI 标题.

per Owner 2026-06-20 18:03 + 18:05 拍板铁律:
- 高优先级可疑关键词: pass | password | key | flag | f1ag | p@ssw0rd | secret | ctf
- 大小写不敏感
- 子串匹配 (不用 \\\\b 边界)
- 命中 → severity=5 SP → 进 GUI "可疑点列表"
- length 降序 (password 先于 pass, 避免 pass 吃掉 password)

修前 bug (per Owner 18:03 实测 misc2.jpg):
- 旧实现 \\\\b(?:` + kws + `)\\\\b` → `this_is_not_password` 漏匹配 (因为 `_` 是 word char)
- exiftool adapter 走 scan_output_for_suspicious → 没生成 SP → journal 没收到
- 修后: 子串匹配 + IGNORECASE → 命中 SP severity=5 → journal 收到
"""
from __future__ import annotations

import pytest

from automisc.core.suspicious import (
    KEYWORDS,
    SEVERITY_MAP,
    _keyword_pattern,
    scan_output_for_suspicious,
)


# ---------- Owner 铁律白名单 ----------

class TestOwnerKeywordWhitelist:
    """owner 拍板的 8 个高优先级 keyword 必须全部在 KEYWORDS 列表里."""

    def test_required_keywords_all_present(self):
        """per Owner 18:05 拍板: pass/password/key/flag/f1ag/p@ssw0rd/secret/ctf 必须全在."""
        required = {"pass", "password", "key", "flag", "f1ag", "p@ssw0rd", "secret", "ctf"}
        missing = required - set(KEYWORDS)
        assert not missing, f"Owner 拍板的高优先级 keyword 缺失: {missing}"

    def test_keyword_pattern_is_case_insensitive(self):
        """IGNORECASE 必须开 (F1AG / PASS / Password 都要命中)."""
        pat = _keyword_pattern()
        for text in ["PASSWORD", "password", "Password", "PassWord", "F1AG", "f1ag", "Flag"]:
            assert pat.search(text), f"{text!r} 没命中 (IGNORECASE 没开)"


# ---------- 子串匹配 (不是 \b) ----------

class TestSubstringMatching:
    """owner 拍板: 子串匹配, 不用 word boundary.

    实战场景: `this_is_not_password` 的 `password` 前面是 `_`,
    旧 \\\\b 边界漏掉, 修后子串匹配命中.
    """

    def test_underscore_prefix_password(self):
        """`this_is_not_password` → 必须命中 (owner 实战 bug)."""
        sps = scan_output_for_suspicious(
            tool_name="exiftool", file_path="/x", stdout="XP Comment : this_is_not_password"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        assert len(kw_sps) >= 1, f"this_is_not_password 漏匹配, sps={sps}"
        # 匹配到 password 或 pass 都算 (但 prefer password 长 keyword)
        assert any(sp.matched_pattern.lower() == "password" for sp in kw_sps), (
            f"expected to match 'password' (longer), got {[sp.matched_pattern for sp in kw_sps]}"
        )

    def test_passphrase_substring_match(self):
        """`passphrase` 包含 `pass` → 命中 (子串匹配)."""
        sps = scan_output_for_suspicious(
            tool_name="t", file_path="/x", stdout="the passphrase is: 1234"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        assert len(kw_sps) >= 1
        assert any(sp.matched_pattern.lower() == "pass" for sp in kw_sps)

    def test_keyword_in_middle_of_word(self):
        """`the_password_field` → password 命中."""
        sps = scan_output_for_suspicious(
            tool_name="t", file_path="/x", stdout="the_password_field = 'secret'"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        keywords_matched = {sp.matched_pattern.lower() for sp in kw_sps}
        assert "password" in keywords_matched
        assert "secret" in keywords_matched


# ---------- 长 keyword 优先 (length 降序) ----------

class TestLengthDescending:
    """regex alternatives 按顺序匹配, 必须长的在前, 否则 password 被 pass 截短."""

    def test_password_not_truncated_to_pass(self):
        """`password=hunter2` → 必须匹配 `password`, 不能只匹配 `pass`."""
        sps = scan_output_for_suspicious(
            tool_name="t", file_path="/x", stdout="config: password=hunter2"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        keywords_matched = [sp.matched_pattern.lower() for sp in kw_sps]
        # 必须有 password (不是只 pass)
        assert "password" in keywords_matched, (
            f"password should match 'password' (not just 'pass'), got {keywords_matched}"
        )

    def test_p0ssw0rd_not_truncated(self):
        """`p@ssw0rd` (8 字符) → 必须匹配完整, 不能只匹配 `pass` (4 字符)."""
        sps = scan_output_for_suspicious(
            tool_name="t", file_path="/x", stdout="the p@ssw0rd hint: st3g0"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        keywords_matched = [sp.matched_pattern for sp in kw_sps]
        assert "p@ssw0rd" in keywords_matched, f"got {keywords_matched}"


# ---------- severity=5 (per Owner 铁律) ----------

class TestKeywordSeverityIs5:
    """keyword 命中 SP severity 必须 = 5 (高优先级可疑)."""

    def test_keyword_severity_is_5(self):
        """SEVERITY_MAP['keyword'] = (5, ...)."""
        sev, action = SEVERITY_MAP["keyword"]
        assert sev == 5, f"keyword severity 应为 5 (per Owner 18:03), got {sev}"
        assert "可疑" in action or "pass" in action.lower() or "key" in action.lower()

    def test_keyword_sp_has_severity_5(self):
        """scan_output_for_suspicious 返回的 keyword SP severity=5."""
        sps = scan_output_for_suspicious(
            tool_name="t", file_path="/x", stdout="XP Comment : this_is_not_password"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        assert all(sp.severity == 5 for sp in kw_sps), (
            f"keyword SP severity 应为 5, got {[sp.severity for sp in kw_sps]}"
        )


# ---------- owner 变种关键字覆盖 ----------

class TestOwnerVariants:
    """owner 拍板的变种必须全部命中."""

    @pytest.mark.parametrize("text,expected", [
        ("the password is 1234", ["password"]),
        ("PASSWORD=abc", ["PASSWORD"]),  # 大写
        ("p@ssw0rd is here", ["p@ssw0rd"]),
        ("this is f1ag{...}", ["f1ag"]),
        ("F1AG match", ["F1AG"]),  # 大写
        ("secret key", ["secret", "key"]),
        ("ctf{abc}", ["ctf"]),  # 整段 flag regex 也命中
        ("the pass", ["pass"]),
        ("PassWord", ["Pass"]),  # Word 里有 Pass, 命中
    ])
    def test_owner_variants_hit(self, text, expected):
        sps = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout=text)
        matched = [sp.matched_pattern for sp in sps if sp.category == "keyword"]
        for exp in expected:
            assert any(exp.lower() in m.lower() for m in matched), (
                f"text={text!r}: expected {exp!r} in matched={matched}"
            )


# ---------- GUI 标题 (per Owner 18:03 拍板) ----------

class TestJournalPanelTitle:
    """journal_panel 标题必须是 '可疑点列表' (per Owner 拍板), 不是 'Journal (可疑点累积)'."""

    def test_journal_panel_title_is_chinese(self, qapp):
        """实例化 JournalPanel 检查 windowTitle == '可疑点列表'."""
        pytest.importorskip("PySide6")
        from automisc.gui.journal_panel import JournalPanel
        panel = JournalPanel()
        assert panel.windowTitle() == "可疑点列表", (
            f"journal_panel 标题应为 '可疑点列表', got {panel.windowTitle()!r}"
        )

    def test_journal_panel_title_not_old_english(self, qapp):
        """旧标题 'Journal (可疑点累积)' 必须不复存在."""
        pytest.importorskip("PySide6")
        from automisc.gui.journal_panel import JournalPanel
        panel = JournalPanel()
        assert "Journal" not in panel.windowTitle(), (
            f"旧标题含 'Journal', got {panel.windowTitle()!r}"
        )