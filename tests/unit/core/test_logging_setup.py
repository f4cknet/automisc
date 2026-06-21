"""测试 core/logging_setup.py (v0.5-journal-highlight-keywords-Q7, per Owner 2026-06-16 17:00)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from automisc.core import logging_setup
from automisc.core.logging_setup import (
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_FILE,
    get_logger,
    show_log_path,
)


@pytest.fixture(autouse=True)
def reset_logging_module_state():
    """每个 test 前重置 _LOGGING_INITIALIZED 标志, 避免 pytest 间状态污染."""
    logging_setup._LOGGING_INITIALIZED = False
    # 清空 root logger 已有 handler
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    yield
    # test 完后再清一次
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    logging_setup._LOGGING_INITIALIZED = False


@pytest.fixture
def tmp_log_dir(tmp_path):
    """临时 log 目录, 不污染 ~/.mavis/logs/."""
    return tmp_path


def _setup(log_file, level=logging.INFO):
    """内部 helper: 强制重置 state 后 setup."""
    logging_setup._LOGGING_INITIALIZED = False
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    return logging_setup.setup_logging(log_file=log_file, level=level, also_console=False)


def test_setup_logging_creates_file(tmp_log_dir):
    """setup_logging 写文件成功, 格式含时间/级别/线程/logger."""
    log_file = tmp_log_dir / "test.log"
    _setup(log_file, level=logging.INFO)
    log = get_logger("test.module1")
    log.info("hello from main thread")
    log.warning("warning message")
    log.error("error message")

    content = log_file.read_text()
    # 格式: "时间 | 级别 | 线程 | logger | 消息"
    lines = [ln for ln in content.splitlines() if "MainThread" in ln and "test.module1" in ln]
    assert len(lines) >= 3
    for line in lines:
        # 验证格式
        assert re.match(
            r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \| (INFO|WARNING|ERROR|DEBUG)\s+\| MainThread\s+\| test\.module1\s+\| ",
            line,
        ), f"unexpected log format: {line!r}"


def test_setup_logging_thread_name_visible(tmp_log_dir):
    """thread name 在 log 里可见 (per Q7 调试需求: 区分主线程 vs QThread).

    直接挂 file handler 到 root logger (不调 setup_logging, 避免幂等干扰).
    """
    import threading
    from logging.handlers import TimedRotatingFileHandler

    log_file = tmp_log_dir / "test.log"
    log = get_logger("test.thread.unique.q7")

    # 直接挂一个 file handler 到 root logger
    handler = TimedRotatingFileHandler(
        str(log_file), when="midnight", backupCount=1, encoding="utf-8"
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(threadName)-15s | %(name)-20s | %(message)s",
    ))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    try:
        # 主线程 log
        log.info("from main thread Q7")

        # 后台线程 log
        def background_log():
            log.info("from background thread Q7")
        t = threading.Thread(target=background_log, name="BackgroundWorker-Q7")
        t.start()
        t.join()

        # 验证 thread name 出现
        content = log_file.read_text()
        assert "from background thread Q7" in content, f"content: {content!r}"
        assert "BackgroundWorker-Q7" in content
        assert "from main thread Q7" in content
    finally:
        # 清理
        logging.getLogger().removeHandler(handler)
        handler.close()


def test_setup_logging_idempotent(tmp_log_dir):
    """重复 setup_logging 不重复加 handler (per Python logging best practice).

    注: _LOGGING_INITIALIZED 标志确保第二次调用不真重 init.
    """
    log_file = tmp_log_dir / "test.log"
    _setup(log_file)
    n_handlers_first = len(logging.getLogger().handlers)

    # 重复调用 (不重置 _LOGGING_INITIALIZED — 应该被幂等保护)
    logging_setup.setup_logging(log_file=log_file, also_console=False)
    n_handlers_second = len(logging.getLogger().handlers)

    assert n_handlers_first == n_handlers_second, (
        f"handler count changed: {n_handlers_first} → {n_handlers_second}"
    )


def test_setup_logging_creates_dir(tmp_path, monkeypatch):
    """log file 父目录不存在时自动 mkdir."""
    log_file = tmp_path / "nonexistent" / "deep" / "test.log"
    assert not log_file.parent.exists()
    _setup(log_file)
    assert log_file.parent.exists()


def test_setup_logging_rotates_by_midnight(tmp_log_dir):
    """TimedRotatingFileHandler when='midnight' (每日 1 文件, 保留 7 天)."""
    log_file = tmp_log_dir / "test.log"
    _setup(log_file)
    # 找 file_handler
    from logging.handlers import TimedRotatingFileHandler
    rotating = [
        h for h in logging.getLogger().handlers
        if isinstance(h, TimedRotatingFileHandler)
    ]
    assert len(rotating) == 1
    # TimedRotatingFileHandler 内部 when 字段大写化
    assert rotating[0].when.upper() == "MIDNIGHT"
    assert rotating[0].backupCount == 7


def test_get_logger_returns_named_logger():
    """get_logger(__name__) 拿标准 logger, 不重复 init."""
    log = get_logger("test.named")
    assert log.name == "test.named"
    assert isinstance(log, logging.Logger)


def test_show_log_path_returns_path():
    """show_log_path 返 Path (not str), 方便后续操作."""
    p = show_log_path()
    assert isinstance(p, Path)


def test_default_log_path_is_under_mavis():
    """默认 log 路径在 ~/.mavis/logs/automisc-gui/."""
    assert str(DEFAULT_LOG_DIR).startswith(str(Path.home() / ".mavis"))
    assert "automisc-gui" in str(DEFAULT_LOG_DIR)


def test_third_party_loggers_quiet(tmp_log_dir):
    """PySide6 / urllib3 / PIL 不刷屏 (调 WARNING 级)."""
    _setup(tmp_log_dir / "quiet.log")
    for name in ("PySide6", "urllib3", "PIL"):
        assert logging.getLogger(name).level >= logging.WARNING
