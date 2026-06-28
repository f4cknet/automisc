"""ChainRunner (v0.5 GUI 完整性)

异步跑 chain（DAG）的 QThread，避免 GUI 主线程卡死。

**vs ToolRunner 区别**：
- ToolRunner 跑单工具 (subprocess + parse)
- ChainRunner 跑整链 (DAG.execute) — 可多 step / 跨工具

**设计**：
- ``ChainRunner(QThread)`` 持有 chain_name / file_path / bruteforce_limit
- 通过 ``finished_with_context`` signal 把 DAG context 传回主线程
- 通过 ``failed_with_error`` signal 报告错误
- 主线程只需 connect signals + runner.start()，不阻塞 UI
"""
from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import QThread, Signal

from automisc.core.dag import Action, ActionResult, DAG


# chain_name -> builder
_CHAIN_BUILDERS = {
    "zip": "build_zip_chain_dag",
    "zip-full": "build_zip_chain_with_bruteforce",
    "binwalk": "build_binwalk_extract_dag",
    "foremost": "build_foremost_extract_dag",
    "lsb": "build_lsb_extract_chain",
    # v0.5-lsb-bytes-gui: lsb-bytes chain (user-controlled 4 参数, 走 extra_context 透传)
    "lsb-bytes": "build_lsb_bytes_chain",
}


# action_name -> Action instance (v0.5 GUI 快捷工具, Owner 加的 4 入口)
_ACTION_REGISTRY: dict[str, Action] = {}


def register_action(name: str, action: Action) -> None:
    """注册 v0.5 快捷 action (lsb_extract / fix_pseudo_zip / bruteforce_zip / bruteforce_rar)."""
    _ACTION_REGISTRY[name] = action


def _ensure_action_registry() -> None:
    """懒加载 v0.5 快捷 action 6 个 (4 老 + 2 v0.5-stegseek 新)."""
    if _ACTION_REGISTRY:
        return
    from automisc.core.actions.lsb_extract import LSBExtractAction
    from automisc.core.actions.rar_chain import BruteforceRarAction
    from automisc.core.actions.stegseek import (
        StegseekCrackAction,
        SteghideExtractAction,
    )
    from automisc.core.actions.zip_chain import (
        BruteforceZipAction,
        FixPseudoEncryptionAction,
    )

    register_action("lsb_extract", LSBExtractAction())
    register_action("fix_pseudo_zip", FixPseudoEncryptionAction())
    register_action("bruteforce_zip", BruteforceZipAction())
    register_action("bruteforce_rar", BruteforceRarAction())
    # v0.5-philosophy-rethink: GUI 工具栏 stegseek 3 模式 (Owner 2026-06-20 13:48 拍板)
    # - stegseek_crack: bruteforce with wordlist (Chain 菜单入口)
    # - steghide_extract: user-provided password (Chain 菜单入口)
    # - 空密码模式: 走 SteghideAdapter (auto_run + ToolMenuDock 共用, 不需 action)
    register_action("stegseek_crack", StegseekCrackAction())
    register_action("steghide_extract", SteghideExtractAction())


class ChainRunner(QThread):
    """QThread 异步跑 chain (DAG) 或 v0.5 快捷 action.

    用法::

        runner = ChainRunner(chain_name="lsb", file_path="/tmp/x.png")
        runner.finished_with_context.connect(self._on_chain_done)
        runner.failed_with_error.connect(self._on_error)
        runner.start()

    链模式: chain_name in {"zip","zip-full","binwalk","foremost","lsb"}
    action 模式: chain_name in {"lsb_extract","fix_pseudo_zip","bruteforce_zip","bruteforce_rar",
                                "stegseek_crack","steghide_extract"}  # v0.5-steghide-GUI 新增

    extra_context 用途 (v0.5-steghide-GUI):
    - {"__wordlist__": path} → StegseekCrackAction 用
    - {"__password__": pw} → SteghideExtractAction 用
    """

    finished_with_context = Signal(str, str, object)  # chain_name, file_path, context
    failed_with_error = Signal(str, str)  # chain_name, error
    started_run = Signal(str, str)  # chain_name, file_path

    def __init__(
        self,
        chain_name: str,
        file_path: str,
        bruteforce_limit: Optional[int] = None,
        extra_context: Optional[dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.chain_name = chain_name
        self.file_path = file_path
        self.bruteforce_limit = bruteforce_limit
        self.extra_context = extra_context or {}
        self._context: Optional[dict[str, Any]] = None
        self._error: Optional[str] = None

    def run(self) -> None:
        """QThread 入口：在子线程跑 chain + emit signals."""
        self.started_run.emit(self.chain_name, self.file_path)
        try:
            _ensure_action_registry()
            from automisc.core.chains import (
                build_binwalk_extract_dag,
                build_foremost_extract_dag,
                build_lsb_bytes_chain,  # v0.5-lsb-bytes-gui
                build_lsb_extract_chain,
                build_zip_chain_dag,
                build_zip_chain_with_bruteforce,
            )

            context: dict[str, Any] = {"file_path": self.file_path}
            if self.bruteforce_limit:
                context["__bruteforce_limit__"] = self.bruteforce_limit
            # v0.5-steghide-GUI: 合并 GUI 传入的 extra context
            # (e.g. __wordlist__ for bruteforce, __password__ for user-pw extract)
            # v0.5-lsb-bytes-gui: __lsb_channels__ / __lsb_bit__ / __lsb_scan_order__ / __lsb_byte_bit_order__
            if self.extra_context:
                context.update(self.extra_context)

            # 模式 1: 6 链 (DAG), v0.5-lsb-bytes-gui 加 lsb-bytes
            chain_builders = {
                "zip": build_zip_chain_dag,
                "zip-full": build_zip_chain_with_bruteforce,
                "binwalk": build_binwalk_extract_dag,
                "foremost": build_foremost_extract_dag,
                "lsb": build_lsb_extract_chain,
                "lsb-bytes": build_lsb_bytes_chain,
            }
            if self.chain_name in chain_builders:
                # v0.5-lsb-bytes-gui: lsb-bytes 是 GUI 第一个带参数的 chain
                # 从 extra_context 抽 4 个 __lsb_* 参数 → 调 build_lsb_bytes_chain(**kwargs)
                if self.chain_name == "lsb-bytes":
                    lsb_kwargs = {
                        "channels": self.extra_context.get("__lsb_channels__"),
                        "bit": int(self.extra_context.get("__lsb_bit__", 0)),
                        "scan_order": self.extra_context.get("__lsb_scan_order__", "row"),
                        "byte_bit_order": self.extra_context.get("__lsb_byte_bit_order__", "MSB"),
                    }
                    dag: DAG = chain_builders[self.chain_name](**lsb_kwargs)
                else:
                    dag: DAG = chain_builders[self.chain_name]()
                context = dag.execute(context)
            # v0.5-lsb-tool-unify Phase 4: lsb_tool action (GUI 工具栏入口)
            # 跟 lsb-bytes 一样从 extra_context 抽 9 个 __lsb_* 参数 → LSBToolAction(**kwargs)
            elif self.chain_name == "lsb_tool":
                from automisc.core.actions.lsb_tool import LSBToolAction
                lsb_kwargs = {
                    "mode": self.extra_context.get("__lsb_mode__", "detect"),
                    "preset": self.extra_context.get("__lsb_preset__"),
                    "channels": self.extra_context.get("__lsb_channels__", "RGB"),
                    "bit": int(self.extra_context.get("__lsb_bit__", 0)),
                    "scan_order": self.extra_context.get("__lsb_scan_order__", "row"),
                    "byte_bit_order": self.extra_context.get("__lsb_byte_bit_order__", "MSB"),
                    "text_min_len": int(self.extra_context.get("__lsb_text_min_len__", 20)),
                    "entropy_threshold": float(self.extra_context.get("__lsb_entropy_threshold__", 5.0)),
                    "unique_threshold": int(self.extra_context.get("__lsb_unique_threshold__", 200)),
                }
                lsb_action = LSBToolAction(**lsb_kwargs)
                result: ActionResult = lsb_action.run(context)
                context["__log__"] = [
                    {
                        "step": 1,
                        "node": lsb_action.name,
                        "success": result.success,
                        "message": result.message,
                    }
                ]
                context["__last_result__"] = result
            # 模式 2: 4 快捷 action (单 Action)
            elif self.chain_name in _ACTION_REGISTRY:
                action = _ACTION_REGISTRY[self.chain_name]
                result: ActionResult = action.run(context)
                # 包成跟 chain 一样的 log schema
                context["__log__"] = [
                    {
                        "step": 1,
                        "node": action.name,
                        "success": result.success,
                        "message": result.message,
                    }
                ]
                context["__last_result__"] = result
            else:
                raise ValueError(
                    f"unknown chain/action: {self.chain_name} "
                    f"(valid: {list(chain_builders.keys()) + list(_ACTION_REGISTRY.keys())})"
                )

            self._context = context
            self.finished_with_context.emit(self.chain_name, self.file_path, context)
        except Exception as e:  # noqa: BLE001
            self._error = str(e)
            self.failed_with_error.emit(self.chain_name, f"{type(e).__name__}: {e}")

    @property
    def context(self) -> Optional[dict[str, Any]]:
        return self._context

    @property
    def error(self) -> Optional[str]:
        return self._error


__all__ = ["ChainRunner"]
