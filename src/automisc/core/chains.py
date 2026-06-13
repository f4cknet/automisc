"""预定义的 chain 模板（v0.5-DAG-chain）

按文件类型 / 工具输出触发对应 chain。
"""

from __future__ import annotations

from automisc.core.actions.binwalk_extract import BinwalkExtractAction
from automisc.core.actions.foremost_extract import ForemostExtractAction
from automisc.core.actions.lsb_extract import LSBExtractAction
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
    """binwalk 分离链 (delegated to binwalk 检测 + foremost 提取):
    binwalk_extract → (success/failure → 终止)
    """
    return DAG(start_node=DAGNode(BinwalkExtractAction()))


def build_foremost_extract_dag() -> DAG:
    """foremost 单独提取链 (skip binwalk detection):
    foremost_extract → (success/failure → 终止)
    """
    return DAG(start_node=DAGNode(ForemostExtractAction()))


def build_lsb_extract_chain() -> DAG:
    """LSB 抽取后智能路由链（v0.5-LSB-router）:
    binwalk_extract → (success/failure → lsb_extract → 终止)

    - binwalk 检测 binwalk/foremost 提取嵌入文件
    - lsb_extract: zsteg 抽 LSB 内容, 分类 (text 终止 / file 二次 router)
    - max_depth=3 防 LSB 死循环
    """
    binwalk_node = DAGNode(BinwalkExtractAction())
    lsb_node = DAGNode(LSBExtractAction(max_depth=3))
    binwalk_node.on_success = lsb_node
    binwalk_node.on_failure = lsb_node  # binwalk 无嵌入也跑 LSB
    lsb_node.on_success = None
    lsb_node.on_failure = None
    return DAG(start_node=binwalk_node)


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
    "build_foremost_extract_dag",
    "build_lsb_extract_chain",
    "find_embedded_archives",
]
