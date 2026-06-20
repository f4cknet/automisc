"""zip_classify adapter (v0.5-zip-verdict-pool)

ZIP 拖入后, 给做题人**明确判断**:
- 伪加密 (可修复) → GUI Fix Zip 伪加密
- 真加密 (需密码) → GUI Zip 暴力破解
- 混合 → 两条都建议
- 全部 clear → 工具栏 unzip 直接解压

**为什么需要这个** (per Owner 2026-06-20 14:13 实测):
"123456cry__foremost/zip/00000038.zip 拖进工具没有提示伪加密.
 按道理 zip 拖进来应该给一个结论, 是伪加密还是真加密, 只有正确的判断,
 做题人下一步才知道去暴力破解还是走伪加密修复"

之前的 FIND_SUSPICIOUS_ARCHIVE_TOOLS 池是 [sevenz / unzip -l / file / strings],
只列文件不判断加密状态. 现在加 zip_classify → per-entry 分类 + verdict.

**功能**:
1. 用 `core.actions.zip_chain._classify_zip_entries` per-entry 分类 (复用 ed5a00c 实现)
2. 自动解压 clear entry (无密码) 到 `<stem>_clear_unzipped/` 目录 (per Owner verdict_silent 拍板)
   - clear 不算雕 (没加密), 不违背 v0.5-philosophy-rethink owner 决策 1
3. 写 1 条 verdict SP (severity 5) + suggested_action 指明 GUI 下一步

**SP schema**:
- category: "zip_encryption_verdict"
- severity: 5 (关键判断, 给做题人指方向)
- matched_pattern: 含 verdict 摘要 + per-entry 详情
- suggested_action: 明确 "GUI Fix Zip 伪加密" / "GUI Zip 暴力破解" 等

**Owner 实测 00000038.zip** (本 commit 验证):
- 1 pseudo (asd/good-已合并.jpg) + 0 real + 2 clear (asd/, asd/qwe.zip)
- verdict: "混合: 1 伪加密 + 0 真加密 + 2 clear"
- action: "伪加密可修复 (GUI Fix Zip 伪加密) | clear 已自动 unzip 到 <stem>_clear_unzipped/"
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from automisc.core.registry import register_tool
from automisc.core.result import ToolResult
from automisc.core.suspicious import SuspiciousPoint
from automisc.core.actions.zip_chain import _classify_zip_entries
from automisc.tools.base import ToolAdapter


@register_tool
class ZipClassifyAdapter(ToolAdapter):
    """`zip_classify` adapter —— ZIP 拖入后给明确 verdict + 自动解压 clear entry.

    per v0.5-zip-verdict-pool (Owner 2026-06-20 14:13 拍板):
    - auto_run 池里跑这个 → 给做题人 verdict (伪加密 / 真加密 / 混合 / clear)
    - clear entry 自动 unzip (无密码, 不算雕) 到 `<stem>_clear_unzipped/`
    - 伪加密 / 真加密 entry 不自动修/爆 — 给建议, 留给 GUI 工具栏 / 链菜单
    """

    name = "zip_classify"
    category = "archive"
    description = (
        "ZIP per-entry 伪加密/真加密/clear 分类 + 自动解压 clear 部分, "
        "verdict SP 给做题人明确下一步 (GUI Fix 或 GUI Bruteforce)"
    )

    default_timeout = 30.0

    def run(self, file_path: str) -> ToolResult:
        zip_path = Path(file_path)

        # 1. 验证是有效 ZIP
        if not zip_path.exists():
            return ToolResult(
                tool_name=self.name,
                exit_code=1,
                stdout="",
                stderr=f"file not found: {zip_path}",
                suspicious_points=[],
            )
        if not zipfile.is_zipfile(zip_path):
            return ToolResult(
                tool_name=self.name,
                exit_code=1,
                stdout="",
                stderr=f"not a valid zip: {zip_path}",
                suspicious_points=[],
            )

        # 2. per-entry 分类 (复用 ed5a00c 实现)
        try:
            classify = _classify_zip_entries(zip_path)
        except Exception as e:
            return ToolResult(
                tool_name=self.name,
                exit_code=1,
                stdout="",
                stderr=f"_classify_zip_entries 失败: {e}",
                suspicious_points=[],
            )

        pseudo_entries = classify.get("pseudo", {})
        real_entries = classify.get("real", {})
        clear_entries = classify.get("clear", {})

        n_pseudo = len(pseudo_entries)
        n_real = len(real_entries)
        n_clear = len(clear_entries)

        # 3. 自动解压 clear entry (per Owner verdict_silent 拍板)
        #    clear 不算雕 (没加密), 不违背 v0.5-philosophy-rethink
        clear_extract_dir = zip_path.parent / f"{zip_path.stem}_clear_unzipped"
        clear_extracted_files: list[str] = []
        if n_clear > 0:
            try:
                clear_extract_dir.mkdir(exist_ok=True)
                with zipfile.ZipFile(zip_path) as zf:
                    for entry_name in clear_entries:
                        # 跳过目录 entry
                        if entry_name.endswith("/"):
                            continue
                        try:
                            zf.extract(entry_name, clear_extract_dir)
                            clear_extracted_files.append(
                                str(clear_extract_dir / entry_name)
                            )
                        except Exception as e:
                            # 单个 entry 失败不阻断 (e.g. 权限)
                            pass
            except Exception:
                # unzip 整体失败也不阻断 verdict
                pass

        # 4. 构造 verdict
        if n_pseudo > 0 and n_real > 0:
            verdict_summary = f"混合: {n_pseudo} 伪加密 + {n_real} 真加密 + {n_clear} clear"
            action = (
                f"伪加密 entry 可修复 (GUI Fix Zip 伪加密) | "
                f"真加密 entry 需密码 (GUI Zip 暴力破解 带 wordlist)"
            )
            severity = 5
        elif n_pseudo > 0:
            verdict_summary = f"纯伪加密: {n_pseudo} entries 可修复 (无密码)"
            action = "GUI Fix Zip 伪加密 (全 entry 修复后解压)"
            severity = 5
        elif n_real > 0:
            verdict_summary = f"纯真加密: {n_real} entries 需密码"
            action = "GUI Zip 暴力破解 (Chain 菜单 bruteforce_zip, 4-6 位)"
            severity = 4
        elif n_clear > 0:
            verdict_summary = f"无加密: {n_clear} clear entries"
            action = "工具栏 unzip 直接解压"
            severity = 2
        else:
            verdict_summary = "空 ZIP 或 0 entries"
            action = "无需操作"
            severity = 1

        # 5. per-entry 详情
        detail_lines = []
        if pseudo_entries:
            detail_lines.append(f"伪加密 ({n_pseudo}):")
            for name, (offset, size) in pseudo_entries.items():
                detail_lines.append(f"  - {name} (offset={offset}, size={size})")
        if real_entries:
            detail_lines.append(f"真加密 ({n_real}):")
            for name, (offset, size) in real_entries.items():
                detail_lines.append(f"  - {name} (offset={offset}, size={size})")
        if clear_entries:
            detail_lines.append(f"clear ({n_clear}):")
            for name, (offset, size) in clear_entries.items():
                detail_lines.append(f"  - {name} (offset={offset}, size={size})")
        detail_text = "\n".join(detail_lines) if detail_lines else "(无 entry)"

        # 6. clear 自动解压结果
        clear_extract_text = ""
        if clear_extracted_files:
            clear_extract_text = (
                f"\n\n[自动解压 clear entry 到] {clear_extract_dir}\n"
                f"  - 已提取 {len(clear_extracted_files)} 个文件"
            )
            if len(clear_extracted_files) <= 10:
                for f in clear_extracted_files:
                    clear_extract_text += f"\n  - {f}"
            else:
                for f in clear_extracted_files[:5]:
                    clear_extract_text += f"\n  - {f}"
                clear_extract_text += f"\n  ... (还有 {len(clear_extracted_files) - 5} 个)"

        # 7. 写 verdict SP
        verdict_sp = SuspiciousPoint(
            id="",
            tool_name=self.name,
            file_path=str(zip_path),
            category="zip_encryption_verdict",
            offset=None,
            matched_pattern=(
                f"{verdict_summary}\n\n"
                f"per-entry 详情:\n{detail_text}"
                f"{clear_extract_text}"
            ),
            severity=severity,
            suggested_action=action,
        )

        # 8. 拼 metadata 让 GUI 知道 clear 自动解压路径
        metadata = {
            "pseudo_count": n_pseudo,
            "real_count": n_real,
            "clear_count": n_clear,
            "pseudo_entries": {k: list(v) for k, v in pseudo_entries.items()},
            "real_entries": {k: list(v) for k, v in real_entries.items()},
            "clear_entries": {k: list(v) for k, v in clear_entries.items()},
            "clear_extract_dir": str(clear_extract_dir) if clear_extracted_files else None,
            "clear_extracted_files": clear_extracted_files,
            "verdict_summary": verdict_summary,
        }

        return ToolResult(
            tool_name=self.name,
            exit_code=0,
            stdout=f"verdict: {verdict_summary}",
            stderr="",
            suspicious_points=[verdict_sp],
            metadata=metadata,
        )


__all__ = ["ZipClassifyAdapter"]
