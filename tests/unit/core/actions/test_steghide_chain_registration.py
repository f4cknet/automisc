"""测试 core/actions/steghide_crack / steghide_extract 注册到 _ACTION_REGISTRY (v0.5-stegseek-remove).

替代原 test_stegseek.py 中 test_stegseek_actions_registered_in_chain_runner,
改测 steghide_crack + steghide_extract 在 chain_runner 的注册.
"""
from __future__ import annotations


def test_steghide_actions_registered_in_chain_runner():
    """steghide_crack + steghide_extract 必须注册到 _ACTION_REGISTRY (ChainRunner 用)."""
    from automisc.gui.chain_runner import _ensure_action_registry, _ACTION_REGISTRY
    _ensure_action_registry()
    assert "steghide_crack" in _ACTION_REGISTRY, (
        f"steghide_crack 必须注册 (v0.5-stegseek-remove 替代 stegseek_crack), "
        f"当前: {list(_ACTION_REGISTRY.keys())}"
    )
    assert "steghide_extract" in _ACTION_REGISTRY, (
        f"steghide_extract 必须注册, 当前: {list(_ACTION_REGISTRY.keys())}"
    )
    # v0.5-stegseek-remove: stegseek_crack 必须删
    assert "stegseek_crack" not in _ACTION_REGISTRY, (
        f"stegseek_crack 已删 (v0.5-stegseek-remove), "
        f"残留: {list(_ACTION_REGISTRY.keys())}"
    )
