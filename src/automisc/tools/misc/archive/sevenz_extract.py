"""7z extract adapter (v0.5-sevenz-extract).

``7z`` 解压工具 — 真正执行 ``7z x`` 把 archive 解到 input 同目录.

per Owner 2026-06-20 19:48 拍板, 参照 writeup:
https://www.cnblogs.com/junlebao/p/13837046.html (面具下的flag, flag.vmdk)

7z CLI 强项 (p7zip 17.05 supports):
- 30+ 格式: zip / 7z / rar / tar / gz / bz2 / xz / wim / iso / vmdk / vdi / vhd / ova ...
- writeup: ``7z x flag.vmdk -o/`` 解 vmdk

**与 sevenz adapter 关系**:
- ``sevenz`` (探测) — ``7z l`` list + ``7z t`` test, 不解压 (per v0.5-philosophy-rethink 探测归探测)
- ``sevenz_extract`` (解压) — ``7z x`` 真正解压, GUI 工具栏触发, 写盘到 input 同目录

**对称性**:
- ``unzip`` adapter 也只 list 不解压 (真解压走 chain)
- 本 adapter 是 unzip / sevenz 的 "解压版", 跟 zip_classify 配对

**v0.5-output-samedir 铁律**: 解到 ``<input_stem>__7z_extracted/`` (跟 input 同目录)

**macOS**: ``brew install p7zip`` (已装, per tools.md §3.9)
"""
from __future__ import annotations

import shutil

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint, scan_output_for_suspicious
from automisc.core.utils.output_path import extract_dir_for
from automisc.tools.base import ToolAdapter
from automisc.tools.paths import resolve_tool_binary


# 7z x 报错的强信号: 加密 / 损坏 / 伪加密
_EXTRACT_ERROR_HINTS = [
    "Wrong password",      # 真加密 (密码错)
    "Headers Error",       # 伪加密 (flag 位异常)
    "cannot open the file as archive",  # 不是归档
    "Data Error",          # 损坏
    "Encrypted = +",       # 标记加密但没密码
    "ERROR:",              # 7z 通用错误前缀
]


@register_tool
class SevenZipExtractAdapter(ToolAdapter):
    """`7z` extract adapter —— 真正执行 `7z x` 解压到 input 同目录.

    per Owner 2026-06-20 19:48 拍板 (writeup 面具下的flag):
    - GUI 工具栏 "Misc/Archive" 下新增入口 "📦 7z 解压"
    - 解到 `<input_stem>__7z_extracted/` (per v0.5-output-samedir)
    - 不动 sevenz adapter (探测) — 两个 adapter 职责分离
    """

    name = "sevenz_extract"
    category = "misc_archive"
    description = "7-Zip 解压 — 真正 `7z x` 解压到 input 同目录 (zip/7z/rar/tar/vmdk/vhd/wim 等 30+ 格式)"

    default_timeout = 120.0  # 解压可能慢 (大文件 / VMDK)

    def run(self, file_path: str) -> ToolResult:
        """执行 `7z x -y -o<dir> <file>` 解压.

        Args:
            file_path: 待解压文件绝对路径 (zip/7z/rar/vmdk 等)

        Returns:
            ToolResult with:
            - stdout: 7z x 输出
            - suspicious_points:
              - severity=5 archive_extracted (成功): "extracted N files to <dir>"
              - severity=4 archive_pseudo_encryption (伪加密): Headers Error
              - severity=4 archive_encrypted (真加密): Wrong password
              - severity=3 archive_error (损坏/非归档): Data Error / cannot open
            - metadata.written_files: 解压目录路径 (per v0.5-hex-router-journal 模式)
        """
        # 1. 准备 output 目录 (per v0.5-output-samedir)
        extract_dir = extract_dir_for(file_path, purpose="7z_extracted")
        if extract_dir.exists():
            shutil.rmtree(extract_dir)  # 7z x 不覆盖, 先清旧的
        extract_dir.mkdir(parents=True, exist_ok=True)

        # 2. 构造 7z x 命令 (per writeup: 7z x flag.vmdk -o/)
        #    -o<dir> 直接连, 无空格 (7z 风格)
        #    -y assume Yes (避免交互)
        cmd = [
            self.binary_path or resolve_tool_binary("7z") or "7z",
            "x",
            "-y",
            f"-o{extract_dir}",
            file_path,
        ]
        exit_code, stdout, stderr, duration_ms = self._run_subprocess(cmd, timeout=self.default_timeout)

        suspicious: list[SuspiciousPoint] = []
        combined = (stdout + "\n" + stderr)

        # 1. 通用扫描 (owner 铁律: 关键字命中 = 可疑)
        suspicious.extend(scan_output_for_suspicious(
            tool_name=self.name, file_path=file_path, stdout=stdout,
        ))

        # 2. 成功信号: 7z x 退出码 0 + output 目录有文件
        if exit_code == 0 and extract_dir.exists():
            extracted_files = list(extract_dir.rglob("*"))
            file_count = sum(1 for p in extracted_files if p.is_file())
            if file_count > 0:
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="archive_extracted",
                        offset=None,
                        matched_pattern=f"7z extracted {file_count} files to {extract_dir}",
                        severity=5,  # 关键成功信号 (跟 keyword 同级)
                        suggested_action=(
                            f"解压成功, 输出目录: {extract_dir} — "
                            f"用 finder 打开 / 继续跑 auto_run 解出的文件"
                        ),
                    )
                )
            else:
                # 退出 0 但目录空: 异常 (7z 通常不会, 但兜底)
                suspicious.append(
                    SuspiciousPoint(
                        id="",
                        tool_name=self.name,
                        file_path=file_path,
                        category="archive_empty",
                        offset=None,
                        matched_pattern=f"7z x exit 0 但 output 目录为空: {extract_dir}",
                        severity=3,
                        suggested_action="7z 异常退出 0 但没解出文件, 检查 archive 是否为空",
                    )
                )

        # 3. 失败信号: 7z x 退出码非 0
        #    注意 (跟 sevenz.py 一致): 7z 对伪加密 zip 报 "Wrong password",
        #    因为 7z 跟 python zipfile 一样只看 LFH flag bit0 (不区分真/假加密).
        #    所以 "Wrong password" 默认当伪加密信号 (severity=4, archive_pseudo_encryption).
        if exit_code != 0:
            combined_lower = combined.lower()
            severity = 3  # 默认
            category = "archive_error"
            action = "7z 解压失败, 检查 archive 完整性 / 是否伪加密 / 是否真加密"

            # 3a. 伪加密 (Headers Error) — 强信号 severity 4
            if "headers error" in combined_lower:
                severity = 4
                category = "archive_pseudo_encryption"
                action = (
                    "7z 伪加密信号: 建议 hexedit 改 flag 位 (0x09 → 0x00) "
                    "或 foremost 提取后修复"
                )
            # 3b. "Wrong password" 默认判伪加密 (跟 sevenz.py 一致)
            #     7z 跟 zipfile 一样只看 flag bit0, 不能区分真/假加密
            elif "wrong password" in combined_lower or "encrypted = +" in combined_lower:
                severity = 4
                category = "archive_pseudo_encryption"
                action = (
                    "7z 报 Wrong password (大概率伪加密 — 7z 跟 zipfile 一样只看 LFH flag bit0): "
                    "建议 hexedit 改 flag 位 (0x09 → 0x00) 后重试; "
                    "若确认真加密, GUI 工具栏 john 爆破"
                )
            # 3c. 损坏 / 非归档 — severity 3
            elif "cannot open" in combined_lower or "data error" in combined_lower:
                severity = 3
                category = "archive_error"
                action = "7z 报告 archive 损坏 / 非归档格式, 检查文件完整性"

            matched = next(
                (h for h in _EXTRACT_ERROR_HINTS if h.lower() in combined_lower),
                f"7z x 退出码 {exit_code}",
            )
            suspicious.append(
                SuspiciousPoint(
                    id="",
                    tool_name=self.name,
                    file_path=file_path,
                    category=category,
                    offset=None,
                    matched_pattern=f"7z x: {matched}",
                    severity=severity,
                    suggested_action=action,
                )
            )

        # 4. 构造 ToolResult
        result = ToolResult(
            tool_name=self.name,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            suspicious_points=suspicious,
            duration_ms=duration_ms,
        )

        # 5. 成功时记录解压目录到 metadata (GUI/chain 可读, v0.5-hex-router-journal 模式)
        if exit_code == 0 and extract_dir.exists():
            extracted_files = list(extract_dir.rglob("*"))
            file_count = sum(1 for p in extracted_files if p.is_file())
            if file_count > 0:
                result.add_written_file(
                    path=str(extract_dir),
                    kind="7z 解压目录",
                    source=self.name,
                )

        return result