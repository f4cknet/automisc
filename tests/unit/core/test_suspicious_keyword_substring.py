"""测试 core/suspicious.py + gui/journal_panel.py — keyword 子串匹配 + severity 5 + GUI 标题.

per Owner 2026-06-20 18:03 + 18:05 + 19:39 拍板铁律:
- 高优先级可疑关键词 (11 个): pass | password | key | flag | f1ag | p@ssw0rd | p@ssphrase | fl@g | s3cr3t | secret | ctf
- 大小写不敏感
- 子串匹配 (不用 \\b 边界)
- 命中 → severity=5 SP → 进 GUI "可疑点列表"
- length 降序 (password 先于 pass, 避免 pass 吃掉 password)

修前 bug (per Owner 18:03 实测 misc2.jpg):
- 旧实现 \\b(?:` + kws + `)\\b` → `this_is_not_password` 漏匹配 (因为 `_` 是 word char)
- exiftool adapter 走 scan_output_for_suspicious → 没生成 SP → journal 没收到
- 修后: 子串匹配 + IGNORECASE → 命中 SP severity=5 → journal 收到

实战累积 (per Owner 19:39): 加 p@ssphrase / fl@g / s3cr3t
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
        """per Owner 18:05 + 19:39 拍板: 11 个高优先级 keyword 必须全在."""
        required = {
            "pass", "password", "key", "flag", "f1ag", "p@ssw0rd",
            "p@ssphrase", "fl@g", "s3cr3t",
            "secret", "ctf",
        }
        missing = required - set(KEYWORDS)
        assert not missing, f"Owner 拍板的高优先级 keyword 缺失: {missing}"

    def test_keyword_pattern_is_case_insensitive(self):
        """IGNORECASE 必须开 (F1AG / PASS / Password / P@SSPHRASE / FL@G / S3CR3T 都要命中)."""
        pat = _keyword_pattern()
        for text in [
            "PASSWORD", "password", "Password", "PassWord",
            "F1AG", "f1ag", "Flag",
            "P@SSPHRASE", "p@ssphrase", "P@ssphrase",
            "FL@G", "fl@g", "Fl@g",
            "S3CR3T", "s3cr3t", "S3cr3t",
        ]:
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


# ---------- Owner 19:39 实战累积变种 (p@ssphrase / fl@g / s3cr3t) ----------

class TestOwnerV2Variants:
    """per Owner 2026-06-20 19:39 拍板: 实战累积加 3 个 keyword 变种.

    - p@ssphrase — pass 的常见变形 (p@ss + phrase)
    - fl@g — flag 的常见变形 (f + l + @ + g)
    - s3cr3t — secret 的 leetspeak 变形 (s3cr3t)
    """

    @pytest.mark.parametrize("text,expected", [
        # p@ssphrase — 9 字符, 必须完整匹配 (不被 pass 截短)
        ("the p@ssphrase is: 1234", ["p@ssphrase"]),
        ("P@SSPHRASE = abc", ["P@SSPHRASE"]),  # 大写
        ("MyP@ssphraseHint", ["p@ssphrase"]),  # 嵌入单词
        # fl@g — flag 的 @ 变形
        ("fl@g{hidden}", ["fl@g"]),
        ("FL@G", ["FL@G"]),  # 大写
        ("the fl@g is here", ["fl@g"]),
        # s3cr3t — secret 的 leetspeak 变形
        ("s3cr3t message", ["s3cr3t"]),
        ("S3CR3T", ["S3CR3T"]),  # 大写
        ("the_s3cr3t_key", ["s3cr3t", "key"]),  # 多 keyword 共存
    ])
    def test_owner_v2_variants_hit(self, text, expected):
        """每个变种 keyword 都能被命中, 且大小写不敏感."""
        sps = scan_output_for_suspicious(tool_name="t", file_path="/x", stdout=text)
        matched = [sp.matched_pattern for sp in sps if sp.category == "keyword"]
        for exp in expected:
            assert any(exp.lower() in m.lower() for m in matched), (
                f"text={text!r}: expected {exp!r} in matched={matched}"
            )

    def test_p0ssphrase_not_truncated_to_pass(self):
        """`p@ssphrase` (9 字符) 必须匹配完整, 不被 `pass` (4 字符) 截短.

        length 降序铁律: p@ssphrase (9) > password (8) > p@ssw0rd (8) > pass (4).
        sorted by len reverse=True → p@ssphrase 排第 1, 先匹配, 不会落到 pass.
        """
        sps = scan_output_for_suspicious(
            tool_name="t", file_path="/x", stdout="config: p@ssphrase=hello-world"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        keywords_matched = [sp.matched_pattern for sp in kw_sps]
        assert "p@ssphrase" in keywords_matched, (
            f"p@ssphrase should match full (not truncated to pass), got {keywords_matched}"
        )
        # 不能只有 pass — 必须有 p@ssphrase
        assert any("p@ssphrase" in m for m in keywords_matched)

    def test_s3cr3t_not_truncated_to_secret(self):
        """`s3cr3t` (6 字符) 不被 `secret` (6 字符) 截短.

        字符差异: s3cr3t 含 `3`, secret 无. 两者不互为子串, 独立匹配.
        """
        sps = scan_output_for_suspicious(
            tool_name="t", file_path="/x", stdout="my s3cr3t code: xyz"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        keywords_matched = [sp.matched_pattern for sp in kw_sps]
        assert "s3cr3t" in keywords_matched, (
            f"s3cr3t should match itself, got {keywords_matched}"
        )

    def test_fl0g_not_truncated_to_flag(self):
        """`fl@g` (4 字符) 跟 `flag` (4 字符) 同长, 互不子串.

        fl@g: f,l,@,g
        flag: f,l,a,g
        @ ≠ a, 两者独立匹配.
        """
        sps = scan_output_for_suspicious(
            tool_name="t", file_path="/x", stdout="the fl@g is hidden"
        )
        kw_sps = [sp for sp in sps if sp.category == "keyword"]
        keywords_matched = [sp.matched_pattern for sp in kw_sps]
        assert "fl@g" in keywords_matched, (
            f"fl@g should match itself, got {keywords_matched}"
        )
        # 不能误匹配 flag (因为 fl@g 里没有 a)
        assert "flag" not in keywords_matched, (
            f"fl@g 不应被误判为 flag, got {keywords_matched}"
        )