"""Python logging 配置 (v0.5-journal-highlight-keywords-Q7, per Owner 2026-06-16 17:00).

GUI 运行时把 main thread + QThread 关键节点写到磁盘 log, Owner 卡死时能 tail -f 定位.

设计原则:
- 单一日志文件 (per session) + 日志轮转 (TimedRotatingFileHandler, 每日 1 文件, 保留 7 天)
- 默认 log 路径: ~/.mavis/logs/automisc-gui/automisc-gui.log
- CLI 可用 --log-file / --log-level 覆盖
- 主线程 (MainThread) + QThread (QThread-1, QThread-2, ...) 都打 threadName
- 不在 Qt widgets 写 (避免 GUI log 把 GUI 卡死)
- per Owner 16:45 卡死 bug: 关键节点 (dropEvent / auto-run 启动 / chain 触发 / QMessageBox 弹) 都打 INFO + threadName
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# 默认 log 路径 (per Owner ~/.mavis/logs/automisc-gui/)
DEFAULT_LOG_DIR = Path.home() / ".mavis" / "logs" / "automisc-gui"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "automisc-gui.log"

# 全局 logger (避免重复 init)
_LOGGING_INITIALIZED = False


def setup_logging(
    log_file: str | Path | None = None,
    level: int = logging.INFO,
    also_console: bool = True,
) -> logging.Logger:
    """初始化 GUI 全局 logging (写文件 + 可选 console).

    Args:
        log_file: log 文件路径, 默认 ~/.mavis/logs/automisc-gui/automisc-gui.log
        level: logging 级别, 默认 INFO
        also_console: 是否同时输出到 stderr (default True, 方便 CLI 调试)

    Returns:
        root logger
    """
    global _LOGGING_INITIALIZED

    if log_file is None:
        log_file = DEFAULT_LOG_FILE
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # root logger
    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复 init (per Python logging 文档)
    if _LOGGING_INITIALIZED:
        return root

    # 格式: 时间 | 级别 | 线程名 | logger 名 | 消息
    fmt = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d | %(levelname)-7s | %(threadName)-15s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler (TimedRotatingFileHandler: 每日 1 文件, 保留 7 天)
    file_handler = TimedRotatingFileHandler(
        str(log_file),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(fmt)
    # v0.5-journal-highlight-keywords-Q7 (per Owner 2026-06-16 17:00):
    # 设 flush 频率高 (每 0.5s flush, 而不是等 buffer 满) - 卡死时能立刻看到最新 log
    if hasattr(file_handler, "setFlushInterval"):
        file_handler.setFlushInterval(0.5)  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    # Console handler (stderr)
    if also_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        console_handler.setFormatter(fmt)
        root.addHandler(console_handler)

    # 第三方库调低 (避免刷屏)
    logging.getLogger("PySide6").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    _LOGGING_INITIALIZED = True

    root.info("=" * 80)
    root.info(f"automisc GUI logging initialized | file={log_file} | level={logging.getLevelName(level)}")
    root.info(f"Python: {sys.version.split()[0]} | pid={os.getpid()}")
    root.info("=" * 80)

    return root


def get_logger(name: str) -> logging.Logger:
    """拿一个 logger, 不重复 init.

    Args:
        name: 通常 __name__
    """
    return logging.getLogger(name)


# 给 Owner 提示的 log 路径
def show_log_path() -> Path:
    """返回当前 log 文件路径, 给 status bar / about dialog 显示."""
    if not _LOGGING_INITIALIZED:
        return DEFAULT_LOG_FILE
    # 找 root logger 的 file handler
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, TimedRotatingFileHandler):
            return Path(h.baseFilename)
    return DEFAULT_LOG_FILE


__all__ = [
    "DEFAULT_LOG_DIR",
    "DEFAULT_LOG_FILE",
    "setup_logging",
    "get_logger",
    "show_log_path",
]
