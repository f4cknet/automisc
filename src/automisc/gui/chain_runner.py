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
}


# action_name -> Action instance (v0.5 GUI 快捷工具, Owner 加的 4 入口)
_ACTION_REGISTRY: dict[str, Action] = {}


def register_action(name: str, action: Action) -> None:
    """注册 v0.5 快捷 action (lsb_extract / fix_pseudo_zip / bruteforce_zip / bruteforce_rar)."""
    _ACTION_REGISTRY[name] = action


def _ensure_action_registry() -> None:
    """懒加载 v0.5 快捷 action 4 个."""
    if _ACTION_REGISTRY:
        return
    from automisc.core.actions.lsb_extract import LSBExtractAction
    from automisc.core.actions.rar_chain import BruteforceRarAction
    from automisc.core.actions.zip_chain import (
        BruteforceZipAction,
        FixPseudoEncryptionAction,
    )

    register_action("lsb_extract", LSBExtractAction())
    register_action("fix_pseudo_zip", FixPseudoEncryptionAction())
    register_action("bruteforce_zip", BruteforceZipAction())
    register_action("bruteforce_rar", BruteforceRarAction())


class ChainRunner(QThread):
    """QThread 异步跑 chain (DAG) 或 v0.5 快捷 action.

    用法::

        runner = ChainRunner(chain_name="lsb", file_path="/tmp/x.png")
        runner.finished_with_context.connect(self._on_chain_done)
        runner.failed_with_error.connect(self._on_error)
        runner.start()

    链模式: chain_name in {"zip","zip-full","binwalk","foremost","lsb"}
    action 模式: chain_name in {"lsb_extract","fix_pseudo_zip","bruteforce_zip","bruteforce_rar"}
    """

    finished_with_context = Signal(str, str, object)  # chain_name, file_path, context
    failed_with_error = Signal(str, str)  # chain_name, error
    started_run = Signal(str, str)  # chain_name, file_path

    def __init__(
        self,
        chain_name: str,
        file_path: str,
        bruteforce_limit: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.chain_name = chain_name
        self.file_path = file_path
        self.bruteforce_limit = bruteforce_limit
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
                build_lsb_extract_chain,
                build_zip_chain_dag,
                build_zip_chain_with_bruteforce,
            )

            context: dict[str, Any] = {"file_path": self.file_path}
            if self.bruteforce_limit:
                context["__bruteforce_limit__"] = self.bruteforce_limit

            # 模式 1: 5 链 (DAG)
            chain_builders = {
                "zip": build_zip_chain_dag,
                "zip-full": build_zip_chain_with_bruteforce,
                "binwalk": build_binwalk_extract_dag,
                "foremost": build_foremost_extract_dag,
                "lsb": build_lsb_extract_chain,
            }
            if self.chain_name in chain_builders:
                dag: DAG = chain_builders[self.chain_name]()
                context = dag.execute(context)
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
