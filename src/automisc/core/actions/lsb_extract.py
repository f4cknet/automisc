"""Action: LSB 抽取后智能路由（v0.5-LSB-router 核心）

逻辑（per upgrade/v0.5-LSB-router.md）:

1. 调 `zsteg <file>` 找出所有 text / file 行
2. 优先级处理:
   a) text 行 (b1,rgb,lsb,xy 等 LSB 优先):
      - 抽 raw text (zsteg -e <channel> <file>)
      - 分类 (encoding_detector.score_text_severity):
        * 含 secret/key/flag/ctf → severity=5 + 终止 (Q3)
        * base64/binary/hex → severity=4 + 终止
        * 普通 text → severity=3 + 打印
   b) file 行 (file: <magic>):
      - 抽 raw file (zsteg -e <channel> <file>)
      - 写 tmp + router.route(tmp) 二次分诊
      - 触发 zip_chain / rar (john) / png (递归)
3. 递归深度保护: max_depth=3 (ctx['_lsb_depth'])
4. 都没找到 → "LSB 通道无敏感内容"

DAG 转移:
  LSBExtract.success → 终止
  LSBExtract.failure → 终止 (or 留给外层 chain 决定)
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from automisc.core.dag import Action, ActionResult
from automisc.core.encoding_detector import score_text_severity
from automisc.core.router import detect_magic


# zsteg 输出行格式: "<bit>,<channel>,<order>,<scan>   .. <type>: <content>"
_ZSTEG_LINE_RE = re.compile(
    r"^(?P<channel>b\d+,\w+,\w+,\w+)\s+\.\.\s+(?P<kind>text|file):\s+(?P<content>.+?)\s*$"
)

# text 优先顺序: b1,rgb,lsb,xy 是最常见 LSB (优先级最高)
# 按 bit depth × channel × order × scan 排, b1 + lsb 优先
_TEXT_CHANNEL_PRIORITY = [
    "b1,rgb,lsb,xy",  # 最常见: RGB LSB
    "b1,r,lsb,xy",  # 单 channel
    "b1,g,lsb,xy",
    "b1,b,lsb,xy",
    "b1,rgba,lsb,xy",
    "b1,rgb,msb,xy",
    "b1,rgb,lsb,yx",
    "b1,bgr,lsb,xy",
    "b2,rgb,lsb,xy",
    "b4,rgb,lsb,xy",
]


def _run_zsteg_detect(file_path: str) -> str:
    """调 zsteg 检测, 返回 stdout."""
    zsteg = shutil.which("zsteg")
    if not zsteg:
        return ""
    r = subprocess.run(
        [zsteg, file_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return r.stdout


def _run_zsteg_extract(file_path: str, channel: str) -> bytes | None:
    """调 zsteg -e 抽出 raw bytes. 失败返回 None."""
    zsteg = shutil.which("zsteg")
    if not zsteg:
        return None
    try:
        r = subprocess.run(
            [zsteg, "-e", channel, file_path],
            capture_output=True,
            timeout=30,
        )
        if r.returncode == 0 and r.stdout:
            return r.stdout
        if r.stderr:
            # zsteg 把 binary 写到 stdout, error 到 stderr
            return r.stdout if r.stdout else None
    except (subprocess.TimeoutExpired, OSError):
        return None
    return None


def _parse_zsteg_lines(stdout: str) -> list[dict[str, str]]:
    """解析 zsteg 输出行."""
    results = []
    for line in stdout.splitlines():
        m = _ZSTEG_LINE_RE.match(line)
        if not m:
            continue
        content = m.group("content")
        if content.startswith('"') and content.endswith('"'):
            content = content[1:-1]
        results.append({
            "channel": m.group("channel"),
            "kind": m.group("kind"),
            "content": content,
        })
    return results


def _pick_first_text_channel(parsed: list[dict[str, str]]) -> dict[str, str] | None:
    """按优先级选 text 行."""
    # 1. 优先按 _TEXT_CHANNEL_PRIORITY
    for priority_ch in _TEXT_CHANNEL_PRIORITY:
        for entry in parsed:
            if entry["kind"] == "text" and entry["channel"] == priority_ch:
                return entry
    # 2. 退而求其次, 取第一个 text 行
    for entry in parsed:
        if entry["kind"] == "text":
            return entry
    return None


def _pick_first_file_channel(parsed: list[dict[str, str]]) -> dict[str, str] | None:
    """选第一个 file 行 (按 zsteg 顺序)."""
    for entry in parsed:
        if entry["kind"] == "file":
            return entry
    return None


def _write_tmp_extracted(extracted: bytes, hint_ext: str = ".bin") -> str:
    """写抽出的 bytes 到 tmp, 返回路径."""
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        prefix="automisc_lsb_",
        suffix=hint_ext,
    )
    tmp.write(extracted)
    tmp.close()
    return tmp.name


class LSBExtractAction(Action):
    """LSB 抽出后智能路由 (text 终止 / file 二次 router).

    Args:
        max_depth: 递归深度保护 (默认 3, 防止 LSB → PNG → LSB → ... 死循环)
    """

    name = "lsb_extract"

    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth

    def run(self, context: dict[str, Any]) -> ActionResult:
        file_path = context.get("file_path")
        if not file_path:
            return ActionResult(
                success=False,
                message="lsb_extract: missing 'file_path' in context",
            )

        # 递归深度保护
        depth = context.get("_lsb_depth", 0)
        if depth >= self.max_depth:
            return ActionResult(
                success=False,
                message=f"lsb_extract: max_depth={self.max_depth} reached, 防止 LSB 死循环",
                data={"max_depth_hit": True},
            )

        if not Path(file_path).exists():
            return ActionResult(
                success=False,
                message=f"lsb_extract: file not found: {file_path}",
            )

        # 1. zsteg 检测
        zsteg_stdout = _run_zsteg_detect(file_path)
        if not zsteg_stdout:
            return ActionResult(
                success=False,
                message="lsb_extract: zsteg 未安装或执行失败",
            )

        parsed = _parse_zsteg_lines(zsteg_stdout)
        if not parsed:
            return ActionResult(
                success=False,
                message="lsb_extract: zsteg 未发现 LSB 内容",
            )

        # 2. text 行 (Owner 决策: 扫所有 text 通道, severity=5 优先停, 都未命中按 zsteg 顺序停)
        text_entries = [e for e in parsed if e["kind"] == "text"]
        if text_entries:
            # 抽 raw + 算 severity
            # 按 zsteg 顺序扫 (b1,rgb,lsb,xy 在前)
            seen_texts: list[dict[str, Any]] = []
            best_sensitive: dict[str, Any] | None = None  # severity=5 命中
            for entry in text_entries:
                raw = _run_zsteg_extract(file_path, entry["channel"])
                if raw is None:
                    text = entry["content"]
                else:
                    try:
                        text = raw.decode("utf-8").rstrip("\x00").strip()
                    except UnicodeDecodeError:
                        text = raw.decode("utf-8", errors="replace").rstrip("\x00").strip()
                severity = score_text_severity(text)
                is_sensitive = severity == 5
                seen_texts.append({
                    "channel": entry["channel"],
                    "text": text,
                    "severity": severity,
                    "sensitive_keyword": is_sensitive,
                    "length": len(text),
                })
                if is_sensitive and best_sensitive is None:
                    best_sensitive = seen_texts[-1]
                    # severity=5 立即停 (Owner 经验: LSB 命中敏感词其他通道无新线索)
                    break

            # 选主输出: severity=5 优先, 否则第一个 text
            main = best_sensitive or seen_texts[0]
            flag_candidate = main["text"] if main["sensitive_keyword"] else None

            return ActionResult(
                success=True,
                data={
                    "lsb_text": {
                        "channel": main["channel"],
                        "text": main["text"],
                        "severity": main["severity"],
                        "sensitive_keyword": main["sensitive_keyword"],
                        "length": main["length"],
                    },
                    "lsb_texts_scanned": seen_texts,  # 扫过的全部通道 (供 GUI 渲染)
                    "lsb_text_found": True,
                    "flag_candidate": flag_candidate,
                },
                message=(
                    f"lsb_extract: 命中 LSB text (channel={main['channel']}, "
                    f"severity={main['severity']}, len={main['length']}, "
                    f"扫描了 {len(seen_texts)} 个 text 通道)"
                    + (" [高亮] 命中敏感关键词" if main["sensitive_keyword"] else "")
                ),
            )

        # 3. file 行 (Q2 二次 router)
        file_entry = _pick_first_file_channel(parsed)
        if file_entry:
            # 抽 raw file
            raw = _run_zsteg_extract(file_path, file_entry["channel"])
            if raw is None:
                return ActionResult(
                    success=False,
                    message=f"lsb_extract: file magic 命中 {file_entry['content']} 但 zsteg -e 失败",
                    data={"lsb_file_magic": file_entry["content"]},
                )

            # 写 tmp
            # 用 detect_magic 决定后缀
            magic = detect_magic(raw)
            ext = ".bin"
            if magic:
                if "ZIP" in magic:
                    ext = ".zip"
                elif "RAR" in magic:
                    ext = ".rar"
                elif "PNG" in magic:
                    ext = ".png"
                elif "JPEG" in magic or "JPG" in magic:
                    ext = ".jpg"
                elif "GIF" in magic:
                    ext = ".gif"
                elif "7z" in magic:
                    ext = ".7z"

            tmp_path = _write_tmp_extracted(raw, hint_ext=ext)

            return ActionResult(
                success=True,
                data={
                    "lsb_file": {
                        "channel": file_entry["channel"],
                        "magic": magic or file_entry["content"],
                        "extracted_path": tmp_path,
                        "size": len(raw),
                    },
                    "extracted_files": [tmp_path],  # 跟 binwalk 输出 schema 一致
                    "lsb_file_found": True,
                    "_lsb_depth": depth + 1,  # 递归深度 +1
                },
                message=(
                    f"lsb_extract: 抽到 LSB file (channel={file_entry['channel']}, "
                    f"magic={magic or file_entry['content']}, size={len(raw)}B) "
                    f"→ {tmp_path}"
                ),
            )

        return ActionResult(
            success=False,
            message="lsb_extract: zsteg 输出无可路由内容",
        )


__all__ = ["LSBExtractAction"]
