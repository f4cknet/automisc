"""DecodeRunner (v0.5-decoder-menu, v0.5+ GUI 同步 CLI)

异步跑 decoder 的 QThread, 跟 ChainRunner 类似但目标是单 decoder (非 DAG).

**vs ChainRunner 区别**：
- ChainRunner: 跑整链 (DAG)
- DecodeRunner: 跑单 decoder (registry 注册的 standalone 工具)

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

        runner = DecodeRunner(decoder_name="base64-image", file_path="/tmp/x")
        runner.finished_with_result.connect(self._on_done)
        runner.failed_with_error.connect(self._on_err)
        runner.start()
    """

    finished_with_result = Signal(str, str, object)  # decoder_name, file_path, result
    failed_with_error = Signal(str, str)  # decoder_name, error
    started_run = Signal(str, str)  # decoder_name, file_path

    def __init__(
        self,
        decoder_name: str,
        file_path: str,
        out_dir: str | None = None,
        keep: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.decoder_name = decoder_name
        self.file_path = file_path
        self.out_dir = out_dir
        self.keep = keep
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
            kwargs: dict[str, Any] = {"file_path": self.file_path}
            if "output_dir" in valid_kwargs and self.out_dir:
                kwargs["output_dir"] = self.out_dir
            if "keep_output" in valid_kwargs:
                kwargs["keep_output"] = self.keep

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
