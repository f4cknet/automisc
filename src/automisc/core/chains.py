"""预定义的 chain 模板（v0.5-DAG-chain）

按文件类型 / 工具输出触发对应 chain。
"""

from __future__ import annotations

from automisc.core.actions.binwalk_extract import BinwalkExtractAction
from automisc.core.actions.zip_chain import (
    BruteforceZipAction,
    FixPseudoEncryptionAction,
    TryUnzipAction,
)
from automisc.core.dag import DAG, DAGNode


def build_zip_chain_dag() -> DAG:
    """ZIP 智能分析链:
    try_unzip → (success → 终止) | (failure → fix_pseudo → 终止 / 不重试避免循环)
    """
    try_node = DAGNode(TryUnzipAction())
    fix_node = DAGNode(FixPseudoEncryptionAction())
    try_node.on_failure = fix_node
    fix_node.on_success = None
    fix_node.on_failure = None
    return DAG(start_node=try_node)


def build_zip_chain_with_bruteforce() -> DAG:
    """ZIP 完整分析链（含爆破）:
    try_unzip → (failure → fix_pseudo → (failure → bruteforce))
    """
    try_node = DAGNode(TryUnzipAction())
    fix_node = DAGNode(FixPseudoEncryptionAction())
    bf_node = DAGNode(BruteforceZipAction())
    try_node.on_failure = fix_node
    fix_node.on_failure = bf_node
    bf_node.on_success = None
    bf_node.on_failure = None
    return DAG(start_node=try_node)


def build_binwalk_extract_dag() -> DAG:
    """binwalk 分离链:
    binwalk_extract → (success/failure → 终止)
    """
    return DAG(start_node=DAGNode(BinwalkExtractAction()))


# ---------- 检测 binwalk 输出含 ZIP / 7z / rar / tar 等 ----------
def find_embedded_archives(binwalk_stdout: str) -> list[str]:
    """从 binwalk 输出找出 archive offsets (e.g. "12345: ZIP archive")."""
    archives: list[str] = []
    for line in binwalk_stdout.splitlines():
        # binwalk 输出格式: "<offset>: <description>"
        if "ZIP archive" in line or "7z archive" in line or "gzip" in line.lower():
            archives.append(line.strip())
    return archives


__all__ = [
    "build_zip_chain_dag",
    "build_zip_chain_with_bruteforce",
    "build_binwalk_extract_dag",
    "find_embedded_archives",
]
