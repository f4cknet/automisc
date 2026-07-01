"""DecodeRunner (v0.5-decoder-menu, v0.5+ GUI 同步 CLI)

异步跑 decoder 的 QThread, 跟 ChainRunner 类似但目标是单 decoder (非 DAG).

**vs ChainRunner 区别**：
- ChainRunner: 跑整链 (DAG)
- DecodeRunner: 跑单 decoder (registry 注册的 standalone 工具)

**v0.5-hex-ascii-fix (2026-06-14)**:
- 接受 `text` 参数: GUI 菜单 hex-ascii 从 input 区取 selection/最后 base 行
  (而不是把 current_file 当 hex 解, 之前会 233KB meihuai.jpg 触发卡死 + 乱码)
- `text` 优先于 `file_path`

**v0.5-pyc-decompiler-buttons (2026-07-01)**:
- 加 `force_version` kwarg 透传 (per `inspect.signature` 自动 kwargs 机制, 跟 custom_table 风格一致)
- main_window 解析 menu_dock entry 后缀 `:py2` / `:py3` → 传 `force_version=2/3` 给 DecodeRunner
- pyc_decompiler 的 `run()` 接 `force_version` 走强制 uncompyle6/decompyle3 路由

**信号**：
- finished_with_result(decoder_name, file_path, result)
- failed_with_error(decoder_name, error)
- started_run(decoder_name, file_path)
"""
from __future__ import annotations

import inspect
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal


class DecodeRunner(QThread):
    """QThread 异步跑单 decoder.

    用法::

        # 文本模式 (v0.5-hex-ascii-fix)
        runner = DecodeRunner(decoder_name="hex-ascii", text="48656c6c6f")

        # 文件模式 (e.g. base64-image)
        runner = DecodeRunner(decoder_name="base64-image", file_path="/Challenge/KEY.exe")
        runner.finished_with_result.connect(self._on_done)
        runner.failed_with_error.connect(self._on_err)
        runner.start()

        # 强制版本 (v0.5-pyc-decompiler-buttons)
        runner = DecodeRunner(
            decoder_name="pyc_decompiler",
            file_path="/Challenge/flag.pyc",
            force_version=2,  # 强制 uncompyle6
        )
    """

    finished_with_result = Signal(str, str, object)  # decoder_name, file_path, result
    failed_with_error = Signal(str, str)  # decoder_name, error
    started_run = Signal(str, str)  # decoder_name, file_path

    def __init__(
        self,
        decoder_name: str,
        file_path: str | None = None,
        text: str | None = None,
        out_dir: str | None = None,
        keep: bool = False,
        custom_table: str | None = None,
        hint_bytes: int | None = None,
        force_version: Optional[int] = None,  # v0.5-pyc-decompiler-buttons: 强制反编译版本 (None/2/3)
        parent=None,
    ):
        super().__init__(parent)
        self.decoder_name = decoder_name
        self.file_path = file_path or "<text>"  # 文本模式占位, 用于信号
        self.text = text
        self.out_dir = out_dir
        self.keep = keep
        self.custom_table = custom_table  # v0.5-base-rot-decoders: base64-custom 用
        self.hint_bytes = hint_bytes  # v0.5-base-rot-decoders: base64-stego 用
        self.force_version = force_version  # v0.5-pyc-decompiler-buttons: pyc_decompiler 强制版本
        self._result: Optional[Any] = None
        self._error: Optional[str] = None

    def run(self) -> None:
        """QThread 入口: 调 decoder.run(**kwargs) + emit signals."""
        self.started_run.emit(self.decoder_name, self.file_path)
        try:
            from automisc.core.decoders.registry import get_decoder

            spec = get_decoder(self.decoder_name)
            if spec is None:
                raise ValueError(f"unknown decoder: {self.decoder_name}")

            # 用 inspect 取 runner 的合法 kwargs
            sig = inspect.signature(spec.run)
            valid_kwargs = set(sig.parameters.keys())
            kwargs: dict[str, Any] = {}
            # v0.5-hex-ascii-fix: text 优先于 file_path
            if "text" in valid_kwargs and self.text is not None:
                kwargs["text"] = self.text
            if "file_path" in valid_kwargs and self.file_path and self.file_path != "<text>":
                kwargs["file_path"] = self.file_path
            if "output_dir" in valid_kwargs and self.out_dir:
                kwargs["output_dir"] = self.out_dir
            if "keep_output" in valid_kwargs:
                kwargs["keep_output"] = self.keep
            # v0.5-base-rot-decoders PR3: base64-custom 用 custom_table
            if "custom_table" in valid_kwargs and self.custom_table is not None:
                kwargs["custom_table"] = self.custom_table
            # v0.5-base-rot-decoders PR3: base64-stego 用 hint_bytes
            if "hint_bytes" in valid_kwargs and self.hint_bytes is not None:
                kwargs["hint_bytes"] = self.hint_bytes
            # v0.5-pyc-decompiler-buttons: pyc_decompiler 用 force_version (None=auto / 2=py2 / 3=py3)
            if "force_version" in valid_kwargs and self.force_version is not None:
                kwargs["force_version"] = self.force_version

            result = spec.run(**kwargs)
            self._result = result
            self.finished_with_result.emit(self.decoder_name, self.file_path, result)
        except Exception as e:  # noqa: BLE001
            self._error = f"{type(e).__name__}: {e}"
            self.failed_with_error.emit(self.decoder_name, self._error)

    @property
    def result(self) -> Optional[Any]:
        return self._result

    @property
    def error(self) -> Optional[str]:
        return self._error


__all__ = ["DecodeRunner"]
