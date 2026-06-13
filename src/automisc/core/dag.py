"""DAG 编排（v0.5 核心层）

按拓扑顺序执行一组 action 节点，支持：
- 串行（默认）
- 并行（指定 batch 节点）
- 失败转移（action 返回 ``ActionResult.success=False`` → 跳到 fail 边）
- 节点间传参（output dict 累积）

设计：
- ``Action`` 抽象基类：``run(context: dict) -> ActionResult``
- ``DAGNode``：包装 Action + success 转移 + failure 转移
- ``DAG``：节点集合 + 执行入口 ``execute(initial_context) -> dict``
- 简单实现：v0.5 不做可视化 / 不做并发 / 不做持久化
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ActionResult:
    """Action 执行结果.

    Attributes:
        success: 是否成功
        data: 返回数据（dict 形式，注入 context 供后续 node 使用）
        message: 人类可读描述
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""


class Action(ABC):
    """DAG Action 抽象基类.

    子类实现 ``run(context)`` 即可.
    """

    name: str = ""

    @abstractmethod
    def run(self, context: dict[str, Any]) -> ActionResult:
        """执行 action; context 是累积 dict（前面 node 的 data）.

        Returns:
            ActionResult(success, data, message)
        """
        raise NotImplementedError


@dataclass
class DAGNode:
    """DAG 节点：Action + 转移边."""

    action: Action
    on_success: Optional["DAGNode"] = None
    on_failure: Optional["DAGNode"] = None
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.action.name or self.action.__class__.__name__


class DAG:
    """DAG 编排器.

    用法::

        extract = DAGNode(ExtractAction())
        try_unzip = DAGNode(TryUnzipAction())
        fix_pseudo = DAGNode(FixPseudoEncryptionAction())
        bruteforce = DAGNode(BruteforceAction())

        extract.on_success = try_unzip
        try_unzip.on_success = None  # 成功终止
        try_unzip.on_failure = fix_pseudo
        fix_pseudo.on_success = try_unzip  # 修复后重试
        fix_pseudo.on_failure = bruteforce
        bruteforce.on_success = None  # 爆破失败终止

        dag = DAG(start_node=extract)
        result = dag.execute({"file_path": "/tmp/x.zip"})
    """

    def __init__(self, start_node: DAGNode, max_steps: int = 20) -> None:
        self.start_node = start_node
        self.max_steps = max_steps  # 防止死循环（fix_pseudo.on_success = try_unzip）

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """顺序执行 DAG.

        Args:
            context: 初始 context dict（含 file_path 等）

        Returns:
            最终 context（含所有 node 累积的 data）
        """
        current: Optional[DAGNode] = self.start_node
        steps = 0
        log: list[dict[str, Any]] = []

        while current is not None:
            if steps >= self.max_steps:
                context["__error__"] = f"max_steps={self.max_steps} exceeded"
                break
            steps += 1

            # 执行当前 node
            result = current.action.run(context)
            log.append(
                {
                    "step": steps,
                    "node": current.name,
                    "success": result.success,
                    "message": result.message,
                }
            )

            # 合并 data 到 context
            context[f"__step_{steps}_{current.name}__"] = result.data
            context["__last_result__"] = result

            # 转移
            if result.success:
                current = current.on_success
            else:
                current = current.on_failure

        context["__log__"] = log
        return context


__all__ = ["Action", "ActionResult", "DAG", "DAGNode"]
