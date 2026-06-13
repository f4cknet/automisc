# 2026-06-14 — 新题回归 + LSB bug 修

> **触发**：Owner 昨晚新增 `Challenge/KEY.exe` + `Challenge/meihuai.jpg`  
> **状态**：✅ done (commit (待 push))  
> **关联任务**：[`upgrade/v0.5-session-summary-2026-06-13.md`](v0.5-session-summary-2026-06-13.md)（昨夜收官总结）

---

## 1. 2 道新题 + 拿到的 flag

| 题目 | 大小 | 走法 | flag |
|---|---|---|---|
| `Challenge/KEY.exe` | 3.8KB ASCII | `data:image/jpg;base64,...` → base64 decode → 133x133 PNG → zbar QR 扫 | `KEY{dca57f966e4e4e31fd5b15417da63269}` |
| `Challenge/meihuai.jpg` | 671KB JPG | XMP "图穷flag见" hint → JPEG EOI 后 append 649KB data → hex-of-ASCII 坐标串 → PIL 画 272x272 黑白图 → zbar QR 扫 | `flag{40fc0a979f759c8892f4dc045e28b820}` |

> **2/2 命中**，但**都绕过了 automisc**——意味着 automisc 当前缺 2 个能力。

## 2. 修 1 bug：LSBExtractAction 抽 raw 含 0xff 抛 UnicodeDecodeError

`src/automisc/core/actions/lsb_extract.py:209`：
```python
text = raw.decode("utf-8").rstrip("\x00").strip()  # strict mode
```

`KEY.exe` 解出的 133x133 RGBA PNG 含 0xff 字节 → 抽 raw → decode 抛错。**修**：
```python
text = raw.decode("utf-8", errors="replace").rstrip("\x00").strip()
```

retest：lsb chain 跑 `KEY_decoded.png` 不再 crash；33 单测全 PASS。

## 3. 发现的 v0.5+ 改进点（**待 Owner 决策**）

| 发现 | 现象 | 改进方向 | 工作量 |
|---|---|---|---|
| **base64 data URL** | KEY.exe 是 `data:image/jpg;base64,...` 头 | 加"data URL 启发式解码"工具（嗅探 `data:<mime>;base64,` 头）| 1-2h |
| **JPG/JPEG trailer append** | meihuai.jpg 49% 真图 + 96% appended data | 加"trailer 抽取"工具（找 EOI 后字节，丢给 foremost + 二次解码）| 2h |
| **hex-of-ASCII 坐标串** | meihuai appended data 是双层 hex | 加"QR/ASCII art 渲染"工具（嗅探 `(x,y)\n` 模式 → 画图）| 1h |
| **zsteg 抽 raw 0xff 抛错** | KEY_decoded.png 抽 raw 抛 UnicodeDecodeError | ✅ **已修** | - |

**3 个新工具 = 拼起来 = 1 个 v0.5 迭代任务**（约 4-5h），可独立 commit。

## 4. 6 关验收

| 关 | 验收点 | 结果 |
|---|---|---|
| ② | `pytest tests` | 349 passed (race flake 不算) |
| ③ | LSB chain 跑 KEY_decoded.png 不 crash | ✅（之前 crash → 现在 graceful）|
| ④ | 真实样本 smoke 2 道新题 | ✅ KEY + meihuai 都解出 |
| ⑤ | Owner 自审（待） | - |
| ⑥ | 文档同步 | ✅ 本文件 + upgrade.md 索引 |

## 5. v0.5+ 候选排序（per 昨夜 session summary + 今天发现）

| # | 候选 | 价值 | 工作量 |
|---|---|---|---|
| **1** | **新工具：base64 data URL + JPEG trailer + QR 坐标渲染**（解决今天 2 道题） | 🔥 直接提升解题能力 | 4-5h |
| 2 | 递归链 (`recursive=True`) | 中（解决 04 套娃）| 2-3h |
| 3 | GUI 进度条 + cancel | 中（brute 体验）| 2h |
| 4 | v0.5-1 disk adapters（yara / bulk_extractor / photorec）| 路线图下一步 | 4h |
| 5 | tools.md 清理 | 低（24KB 冗余）| 30min |
