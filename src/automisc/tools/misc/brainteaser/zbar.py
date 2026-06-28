"""zbar adapter (per `tools.md` §3.11 + v0.5-zbar-windows-install)

QR / 条码识别 (QR / EAN-13 / Code-128 / PDF417 / DataMatrix 等 30+ 格式).

**v0.5-zbar-windows-install** (2026-06-28 23:00 Owner 拍板):
- 之前: `subprocess` 调 `zbarimg --quiet --raw <file>` (CLI)
- 现在: `pyzbar.pyzbar.decode(PIL.Image)` (Py3 ctypes wrapper, Win wheel 自带 zbar DLL)
- output 格式 100% 兼容 `zbarimg --raw` (一行一条解码文本), GUI 入口/单测/`coords_to_qr.py` 内部调用**0 改动**

**为什么不直接装 zbarimg**:
- `zbar` 0.10 (PyPI 2009) 是 Py2 时代 C 扩展, Win 无 wheel, 源码要 MSVC 编译 (实测 2026-06-28 失败: "Microsoft Visual C++ 14.0 or greater is required")
- SourceForge `zbar-0.10-setup.exe` (2010 NSIS) 4 个 mirror 全 200 HTML, 链接失效
- pyzbar 跨平台 wheel 走 ctypes + libzbar 库 = 0 编译 + Win ship DLL (per PyPI 主页: "zbar DLLs are included with the Windows Python wheels")

**Win ship `msvcr120.dll` 部署**:
- libzbar-64.dll (pyzbar 自带) 是 VS 2013 编译, 链 `MSVCR120.dll`
- Win ship 默认没装 VS 2013 redist, 报 "Could not find module 'libiconv.dll' (or one of its dependencies)"
- 解决: install.ps1 把 `extend-tools/bin/win-x64/msvcr120.dll` 复制到 pyzbar site-packages
- `msvcr120.dll` (973KB) 从 MS Office 自带抽, MS 允许随 redist 自由分发, 第三方打包合法
"""
from __future__ import annotations

import re
from typing import List

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.tools.base import ToolAdapter


# zbarimg --raw 输出格式: 一行一条解码文本 (无前缀)
# 我们的 pyzbar 实现保持同样格式, 复用下面解析逻辑
_ZBAR_OUTPUT_RE = re.compile(r"^(?:([\w-]+):)?(.+)$")


@register_tool
class ZbarAdapter(ToolAdapter):
    """`zbarimg` adapter — QR / 条码识别 (per v0.5-zbar-windows-install 走 pyzbar 后端)."""

    name = "zbar"
    category = "misc_brainteaser"
    description = "QR / 条码识别 (pyzbar 后端, 30+ 格式: QR / EAN-13 / Code-128 / PDF417 / DataMatrix)"

    default_timeout = 30.0

    def check_available(self) -> bool:
        """v0.5-zbar-windows-install: check pyzbar importable (not binary in PATH).

        pyzbar 装载链: libzbar-64.dll + libiconv.dll (Win wheel 自带) + msvcr120.dll (extend-tools 部署).
        任何一环缺都 ImportError / OSError, 统一返回 False 即可.
        """
        try:
            import pyzbar.pyzbar  # noqa: F401
            return True
        except (ImportError, OSError):
            return False

    def run(self, file_path: str) -> ToolResult:
        # v0.5-zbar-windows-install: use pyzbar instead of subprocess zbarimg
        # 行为等价: 30+ 格式解码, output 格式 = zbarimg --raw (一行一条文本)
        try:
            from PIL import Image
            from pyzbar.pyzbar import decode as pyzbar_decode
        except ImportError as e:
            return ToolResult(
                tool_name=self.name,
                exit_code=127,
                stdout="",
                stderr=f"pyzbar not installed: {e} (run: pip install pyzbar)",
                suspicious_points=[],
            )

        try:
            img = Image.open(file_path)
            results = pyzbar_decode(img)
        except FileNotFoundError:
            return ToolResult(
                tool_name=self.name,
                exit_code=2,
                stdout="",
                stderr=f"file not found: {file_path}",
                suspicious_points=[],
            )
        except Exception as e:
            # PIL.UnidentifiedImageError for non-image files
            # OSError for libzbar load failure (missing msvcr120.dll)
            return ToolResult(
                tool_name=self.name,
                exit_code=1,
                stdout="",
                stderr=f"decode failed: {type(e).__name__}: {e}",
                suspicious_points=[],
            )

        # 构造 stdout: 跟 zbarimg --raw 行为一致 (一行一条解码文本)
        stdout_lines: List[str] = []
        for r in results:
            data_bytes = r.data
            try:
                data_str = data_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # 二进制 payload (e.g. raw bytes) fallback
                data_str = data_bytes.decode("latin-1", errors="replace")
            stdout_lines.append(data_str)
        stdout = "\n".join(stdout_lines)

        # 复用原 zbar SuspiciousPoint 逻辑 (per tools.md §3.11)
        suspicious: list[SuspiciousPoint] = []
        # 1. 通用扫描 (捕获 flag{...})
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 解析每条识别结果 — 跟原 zbar 行为 1:1 兼容
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # 1) 检测 URL scheme (含 ://)
            url_match = re.match(r"^(https?|ftp|file)://(.+)$", line)
            if url_match:
                code_type, content = url_match.group(1), url_match.group(2)
            else:
                m = _ZBAR_OUTPUT_RE.match(line)
                if not m:
                    continue
                code_type = m.group(1) or "unknown"
                content = m.group(2).strip()

            if not content:
                continue

            # 长度 > 50 的字符串 (可能是 base64/URL)
            if len(content) > 50:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="barcode_long_content",
                        offset=None,
                        matched_pattern=f"{code_type}: {content[:120]!r} (len={len(content)})",
                        severity=2,
                        suggested_action="长字符串可能是 base64/URL/编码内容，建议 base64/hex 解码或访问 URL",
                    )
                )
            # 看起来像 URL (之前 URL scheme 的 content 可能以 / 开头)
            elif content.startswith(("/", "//", "?", "&")) or code_type in ("http", "https", "ftp", "file"):
                full_url = f"{code_type}:{content}" if not content.startswith("//") else f"{code_type}:/{content}"
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="barcode_url",
                        offset=None,
                        matched_pattern=f"{code_type}: {full_url[:120]!r}",
                        severity=2,
                        suggested_action="URL 线索：在浏览器访问或 curl 抓内容",
                    )
                )
            # 短字符串 (正常识别结果)
            else:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="barcode_text",
                        offset=None,
                        matched_pattern=f"{code_type}: {content[:80]!r}",
                        severity=1,
                        suggested_action="记录识别内容",
                    )
                )

        # 3. 报告识别数量
        n = sum(1 for line in stdout.splitlines() if line.strip())
        if n > 0:
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category="barcode_meta",
                    offset=None,
                    matched_pattern=f"识别 {n} 个条码/二维码",
                    severity=1,
                    suggested_action="记录识别数量",
                )
            )

        return ToolResult(
            tool_name=self.name,
            exit_code=0,
            stdout=stdout,
            stderr="",
            suspicious_points=suspicious,
            duration_ms=0,  # pyzbar 无独立计时, GUI 显示 0ms 可接受
        )
