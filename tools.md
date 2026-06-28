# tools.md — AutoMisc 外部工具清单

> **角色**：automisc 可调用的**外部 misc 工具** + **安装指引**单一事实来源
> **状态**：v0.1 启动 + 2026-06-13 分支重整（per `prd.md §4.1 v0.1.0b`）
> **配套文档**：
> - [`AGENTS.md`](./AGENTS.md) — 项目治理
> - [`prd.md`](./prd.md) — 需求 + 任务看板 + 入口分流（[`§5 工具池`](./prd.md) + [`§6 入口分流表`](./prd.md)）
> - [`Architecture.md`](./Architecture.md) — 系统架构 + adapter 模式（[`§3 Core 调度层`](./Architecture.md) + [`§4 工具池层`](./Architecture.md) + [`§6 plug-in 机制`](./Architecture.md)）
>
> **本文档章节**：
> - §0 阅读指引
> - §1 状态图例
> - §2 工具池分类总表（按分支）
> - §3 按分支工具清单（含状态 + 安装指引）
> - §4 Python 包清单（含状态）
> - §5 入口分流与工具路由对照
> - §6 P0 工具优先级（v0.1 必须有 adapter）
> - §7 工具池后续演进（v0.5 / v1.0）
> - §8 变更日志

---

## 0. 阅读指引

| 你是谁 | 先看哪节 |
|---|---|
| **想快速了解工具池覆盖** | §2 总表 + §6 P0 优先级 |
| **想知道某个工具是否已装** | §3 按分支查 |
| **想装某个工具** | §3 安装指引列 |
| **想知道 Python 依赖装了什么** | §4 |
| **想看哪些工具对应哪个 subflow** | §5 |
| **v0.1 必须先做哪几个 adapter** | §6（P0 工具）|

---

## 1. 状态图例

| 图标 | 含义 | 处理建议 |
|---|---|---|
| ✅ | PATH 可直接 `subprocess.run([...])` 调用 | v0.1 直接写 adapter |
| ⚠️ | 源码/jar 在但需额外配置（pyenv shim / python2 wrapper / 需 brew 额外依赖）| v0.1 可写 adapter（带 wrapper 脚本） |
| ❌ | 未安装 / 源码缺失 | v0.1 不写 adapter；按 §3 安装指引手动装 |

> **判断标准**：本表状态基于 Windows 当前环境（2026-06-27 实测 `where` + `import` 抽查），工具链走 `extend-tools/bin/win-x64/`。

---

## 2. 工具池分类总表（按分支 · per `prd.md §4.1 v0.1.0b`）

> **2026-06-13 重大调整**：从"按工具能力分类"（图片隐写/流量/压缩/内存/编码/二进制/音频/文档/二维码 9 个）改为**按"用户面对的题目类型"分支**。

```
MISC（根）
├── Forensics（取证）                  ← 独立分支
│   ├── Memory Forensics（内存取证）
│   ├── Disk Forensics（磁盘取证）
│   ├── Network Forensics（流量取证）
│   └── Log Forensics（日志取证）
├── Steganography（隐写术）
│   ├── Image Stego（图片隐写）
│   ├── Audio Stego（音频隐写）
│   └── Video Stego（视频隐写）
├── Encoding（编码分析）               ← 自编写函数，无外部工具
│   ├── Base 系列
│   ├── 古典密码
│   └── 自定义编码
└── Misc Others（其他）
    ├── 压缩包分析
    ├── Office 文档
    └── 脑洞题
```



**精简后的统计**：

| 一级分支 | 子分支数 | 工具总数（✅/⚠️/❌）| v0.1 P0 adapter |
|---|---|---|---|
| **Forensics** | 4 | 14（**3✅ / 0⚠️ / 11❌**）| 6 |
| **Steganography** | 3 | 22（**4✅ / 0⚠️ / 18❌**）| 8 |
| **Encoding** | 3 | **0**（内置实现）| 0 |
| **Misc Others** | 3 | 10（**4✅ / 0⚠️ / 6❌**）| 3 |
| **共享基础工具** | — | 8（**6✅ / 0⚠️ / 2❌**）| 5 |
| **合计** | 14 | 54（**19✅ / 0⚠️ / 35❌**）| **22** |

> **2026-06-29 更新（per §8 v2.6 + v2.7 + v2.8 + v2.9 + v2.10 + v2.11）**：
> - **v2.6 (PR3-prep)**: Owner 在 `extend-tools/bin/win-x64/` 实装 8 个 Win 二进制（`file.exe` / `7z.exe` / `7zr.exe` / `exiftool.exe` / `foremost.exe` / `vim92/diff.exe` / `vim92/xxd.exe` / `steghide/steghide.exe`），§3 + §6.1 status 标 ✅；其他 ❌ pending
> - **v2.7**: 新增 `strings.exe` + pip `binwalk 2.3.2`；`grep` → PowerShell `Select-String`（Win 内置）；§4 Python 包 11 个 ✅ + 8 个 ❌ pending；新增 `requirements.txt`
> - **v2.8 (scope 收窄)**: `extend-tools/install.ps1` 加 **Stage 0 Rust toolchain 装** (rustup-init stable + minimal profile, 失败 warning continue, idempotent 跳过已装) — Rust 装**保留**（独立价值：未来 cargo install 兜底 / binwalk v3 备选 / ad-hoc 工具编写）；**Stage 1 evtx_dump CLI 撤回** (per Owner 2026-06-28 决策：adapter `src/automisc/tools/forensics/log/evtx_dump.py` 用 `python-evtx` 0.8.1 实现结构化字段访问 + EventID scoring + 命令行关键字匹配, evtx_dump CLI 在 adapter 路径上 0 调用, 实际价值仅 = Owner 手动 grep 的便利；实战 ≥3 道同类命中再升架构 per AGENTS §5.2)。详见 [`upgrade/v0.5-windows-evtx-dump.md`](./upgrade/v0.5-windows-evtx-dump.md)
> - **v2.10**: §3.4 python-evtx 状态 ❌→✅（per Owner 2026-06-28 "更新 python-evtx 在 tools.md 的状态"）；`requirements.txt` 第 12 行已有 `python-evtx==0.8.1`（v2.7 加的, 无需重复添加, Owner 二次确认时同步文档说明）；§2 总表 Forensics 2✅→3✅ / total 18✅/36❌ → 19✅/35❌
> - **v2.11 (本次)**: §3.5 Steganography/Image 加 **lsb_tool** 行（✅ 自研 Python, 3 mode 统一 LSB 工具 detect/extract/extract_bytes, 替代 zsteg + lsb_detect + lsb_extract + lsb_bytes_extract; per [`upgrade/v0.5-lsb-tool-unify.md`](./upgrade/v0.5-lsb-tool-unify.md)）; §6.1 P0 #10 zsteg 备注更新 `lsb_detect` → `lsb_tool` + 链接 spec; Phase 1 spec + Phase 2a detect + Phase 2b extract + Phase 3 adapter + Phase 4 GUI dialog 合并 全部落地（5 commits 2904a3b/5cba63a/d5de9ed/2f6825d/b7b212c）。**不动 §2 总表数字**: lsb_tool 是 Python 实现无独立 binary, 不增 "21→22"。
> - §2 数字为**去重后**统计（54 unique tools）；§3 表格 awk 切片会读到更多行（含跨节重复 + 新增 strings/binwalk）
> - §6.1 P0 列表：8 个 P0 已装（`foremost` / `exiftool` / `file` / `7z` / `steghide` / `xxd` / `strings` / `binwalk`）+ `Select-String`（grep 替代），13 个 P0 工具 pending（v2.9 删 evtx_dump #16）

> **v0.1 P0 实际 adapter 数**：21 个（远超 `prd.md §4.1 v0.1.6` 的 ≥5 要求；v2.9 删 evtx_dump #16）。**按 `AGENTS.md §2.1` 任务粒度（≤400 行 / PR），21 个 P0 adapter 必须分多个 PR 实施，建议每 PR 5-7 个 adapter**。

---

## 3. 按分支工具清单

### 3.1 Forensics / Memory Forensics（内存取证）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **vol.py (Volatility 2)** | ❌ | `misc/volatility2/`（原目录丢失，软链 `automisc/extend_tools/volatility2` 为空） | 内存镜像取证（profiles + plugins） | **v0.1 必须恢复安装**（blocker） |
| **vol3 (Volatility 3)** | ❌ | `pip install volatility3` | 现代内存取证 | v0.5 安装 |
| **strings** | ✅ | `extend-tools/bin/win-x64/strings.exe` 内存字符串提取（含 FLAG / SSH_CLIENT / SESSION_KEY） | P0 |
| **binwalk** | ✅ | `python -m binwalk` 内存镜像内嵌文件提取 | P0 |

### 3.2 Forensics / Disk Forensics（磁盘取证）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **fls / icat / mmls（sleuthkit）** | ❌ | `brew install sleuthkit` | 磁盘镜像文件系统解析（FAT16/NTFS/ext2/...） | v0.5 安装 |
| **photorec** | ❌ | `/usr/local/bin/photorec` | 文件雕刻 + 分区恢复 | P1 · v0.5 候选 |
| **testdisk** | ❌ | `/usr/local/bin/testdisk` | 分区恢复 + 文件系统修复 | P1 · v0.5 候选 |
| **7z** | ✅ | `extend-tools/bin/win-x64/7z.exe` | 磁盘镜像（VMDK/OVA）解压 | P1 |
| **veracrypt** | ❌ | `brew install --cask veracrypt` | TrueCrypt/VeraCrypt 卷挂载 | v1.0 评估 |

### 3.3 Forensics / Network Forensics（流量取证）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **tshark** | ❌ | `/usr/local/bin/tshark` | CLI 抓包 + 协议解析 + `--export-objects http` | P0 · v0.1 必须 |
| **tcpdump** | ❌ | `/usr/sbin/tcpdump` | 原始抓包（速度优先） | P0 · v0.1 必须 |
| **wireshark** | ❌ | `/Applications/Wireshark.app/Contents/MacOS/wireshark` | GUI 流量分析（GUI 调用） | P1 · v0.5 候选 |
| **pcapfix** | ❌ | `/usr/local/bin/pcapfix`（**brew core 无 formula**，从 SourceForge 下源码编译，v0.5-tool-install-batch-1 实施） | 损坏 pcap 修复（缺 magic bytes / 校验和） | v0.5 已装 |
| **aircrack-ng** | ❌ | `/usr/local/bin/aircrack-ng`（v1.7_2，brew install） | WiFi WPA/WEP 破解 | v0.5 已装 |
| **multimon-ng** | ❌ | `brew install multimon-ng` | DTMF / POCSAG 解码 | v0.5 候选 |
| **scapy** | ❌ | pip scapy 2.7.0（v0.5-tool-install-batch-1 实施） | Python pcap 操作 | v0.5 已装 |
| **impacket** | ❌ | pip impacket 0.13.1（v0.5-tool-install-batch-1 实施） | NTLMv2 / Kerberos 解析（PCAP 中的 hashcat 提取） | v0.5 已装 |

### 3.4 Forensics / Log Forensics（日志取证）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **Select-String** | ✅ | PowerShell 内置 | 日志关键字 + 异常分析 | P0 |
| **python-evtx（Python 包）** | ✅ | `pip install python-evtx` 0.8.1（已装，Python 模块 `import Evtx` OK + `requirements.txt` 第 12 行 pinned）。**adapter 走 python-evtx 路径**（src/automisc/tools/forensics/log/evtx_dump.py，结构化字段访问 + EventID scoring + 命令行关键字匹配）| .evtx 解析（Python 模块路径） | P0 · v0.5 已装 |
| **7z** | ✅ | `extend-tools/bin/win-x64/7z.exe` | 解压 .evtx.bz2 / .log.tar.gz 等压缩日志 | 共享 |
| **journalctl（macOS N/A）** | ❌ | Linux 专用 | systemd 日志 | 不装 |

> **evtx_dump CLI** 不在本表（2026-06-28 决策：CLI 不走 install.ps1，adapter 走 python-evtx in-process）。决策依据 + 未来实战触发条件见 [`upgrade/v0.5-windows-evtx-dump.md`](./upgrade/v0.5-windows-evtx-dump.md) §6。

#### 3.4.1 python-evtx Python 模块用法

```python
# 结构化字段提取（自动遍历 EventID / Provider / Data）
import Evtx.Views as e
with Evtx.Evtx("file.evtx") as log:
    for record in log.records():
        print(record.root_element().find("EventID").text)
```


### 3.5 Steganography / Image Stego（图片隐写）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **binwalk** | ✅ | `python -m binwalk` 嵌入文件检测 + 提取 | P0 |
| **zsteg** | ❌ | `/usr/local/bin/zsteg`（**Ruby gem**，不是 Python 包） | PNG/BMP LSB 全通道检测 | P0 |
| **lsb_tool** | ✅ | `src/automisc/core/actions/lsb_tool.py`（自研 Python, **3 mode 统一 LSB 工具**） | PNG LSB 隐写检测 (detect) + 字节流提取 (extract / extract_bytes) | P0 · v0.5-lsb-tool-unify 替代 zsteg + lsb_detect + lsb_extract + lsb_bytes_extract |
| **steghide** | ✅ | `extend-tools/bin/win-x64/steghide/steghide.exe` | JPEG/BMP/WAV/AU 隐写（口令） | P0 |
| **outguess** | ❌ | `/usr/local/bin/outguess` | JPEG 隐写 | P1 · v0.5 候选 |
| **stegdetect** | ❌ | `~/.local/bin/stegdetect` | JPEG 隐写检测（jsteg/OutGuess/F5/AppendX） | P1 · v0.5 候选 |
| **stegseek** | ❌ | `~/.local/bin/stegseek` | steghide 高速口令爆破 | P1 · v0.5 候选 |
| **pngcheck** | ❌ | `/usr/local/bin/pngcheck` | PNG chunk 结构验证 + IDAT / tEXt 分析 | P1 · v0.5 候选 |
| **foremost** | ✅ | `extend-tools/bin/win-x64/foremost.exe` | 图片嵌入文件雕刻 | P0 |
| **exiftool** | ✅ | `extend-tools/bin/win-x64/exiftool.exe` | EXIF 元数据（GPS / Make / Model / Software） | P0 |
| **F5-steganography** | ❌ | `misc/F5-steganography/`（已软链 `automisc/extend_tools/`） | JPEG F5 DCT 系数提取 + 解密 | 需 `java` + 手写 wrapper |
| **stegolsb** | ❌ | `pip install stegolsb` | 通用 LSB 隐写 | v0.5 安装 |
| **stegano** | ❌ | `pip install stegano` | 高级 LSB 工具 | v0.5 安装 |
| **stegcracker** | ❌ | `pip install stegcracker` | steghide 字典爆破 | v0.5 安装 |
| **apngdis** | ❌ | `brew install apngdis` | APNG 帧提取 | v0.5 安装 |
| **deepsound** | ❌ | Windows 工具（Wine） | DeepSound 隐写提取 | v1.0 评估 |

### 3.6 Steganography / Audio Stego（音频隐写）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **ffmpeg** | ❌ | `/usr/local/bin/ffmpeg` | 音频转码 + 频谱生成 + showspectrumpic 滤镜 | P0 · v0.1 必须 |
| **sox** | ❌ | `/usr/local/bin/sox`（brew install，2026-06-14 装） | 音频处理 + spectrogram 生成 + `sox -m` 多轨减法 | P0 · v0.1 必须 |
| **audacity** | ❌ | `brew install --cask audacity` | GUI 音频分析（GUI 调用） | v0.5 安装 |
| **sonic-visualiser** | ❌ | `brew install --cask sonic-visualiser` | GUI 频谱分析 | v0.5 安装 |
| **MP3Stego** | ❌ | `misc/MP3Stego/`（源码） | MP3 隐写（口令） | 需编译 `Decode.exe`（Wine） |
| **steghide** | ✅ | `extend-tools/bin/win-x64/steghide/steghide.exe` | WAV/AU 隐写 | 共享 |
| **deepsound2john.py** | ❌ | GitHub `deepsound2john.py` | DeepSound 哈希提取给 John | v1.0 评估 |

### 3.7 Steganography / Video Stego（视频隐写）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **ffmpeg** | ❌ | `/usr/local/bin/ffmpeg` | 视频帧提取 + 多 stream 分离 + `ffprobe` | P0 · v0.1 必须 |
| **ffprobe** | ❌ | `/usr/local/bin/ffprobe` | 多 stream 视频元数据查询 | P0 |
| **vlc** | ❌ | `brew install --cask vlc` | GUI 视频播放（GUI 调用，验证视觉） | v0.5 安装 |
| **MP4Box（GPAC）** | ❌ | `brew install gpac` | MP4 容器解析 | v0.5 安装 |
| **mediainfo** | ❌ | `brew install mediainfo` | 视频元数据 | v0.5 安装 |

### 3.8 Encoding（编码分析 · 自编写）

> **无外部工具依赖**，全部走 Python 标准库 + `core/encoders/` 内置实现。
>
> 实现位置见 [`Architecture.md §3.5 可疑点扫描器`](./Architecture.md) + [`Architecture.md §4.4` 工具池层 + encoders 子目录](./Architecture.md)。

**实现类（Python 内置）**：

#### 3.8.1 Base 系列（`core/encoders/base.py`）

- base16 / base32 / base36 / base58 / base62 / base64 / base85 / base91 / base92 / base100
- base32768（CJK 基本平面 emoji）/ base65536（Unicode BMP）
- base2048（**fallback to base64** · v0.5+ 仍占位，emoji 实现复杂）
- `xxencode` / `yenc` / `uuencode`（古典）

> **v0.5+ 已补**（per `upgrade/v0.5-base-rot-decoders.md` PR1 完成）：
> - ✅ **base36**（0-9 + a-z）
> - ✅ **base92**（94 个 ASCII 可打印，去掉 `\` 和 `"`）
> - ⚠️ **base100**（**fallback to base64**，100 进制无法表示 256 字节值，CTF 极罕见）
> - ✅ **base32768** / **base65536** 真实现（base65536 依赖 PyPI `base65536`）
> - ✅ **base64 自定义表**（`core/encoders/base_custom.py` · 提供 encode + decode + 自动位移检测）

#### 3.8.2 古典密码（`core/encoders/classical.py`）

- ROT5 / ROT13 / ROT18（ROT13+ROT5）/ ROT47（ASCII 33-126）
- Caesar brute force（穷举 26 个 shift）
- Vigenère（已知 key / 不知道 key）
- Atbash / Pigpen / Keyboard Shift（per ctf-misc/encodings.md）
- Affine / Rail Fence

> **v0.5+ 已补**（per `upgrade/v0.5-base-rot-decoders.md` PR1 完成）：
> - ✅ **ROT5**（digits 0-9 旋转）
> - ✅ **ROT47**（ASCII 33-126 整段旋转）
> - ✅ **ROT18**（ROT13+ROT5 组合）

#### 3.8.3 自定义编码（`core/encoders/custom.py`）

- BCD（Binary-Coded Decimal，每个 nibble 一位十进制）
- IEEE 754 Float（`struct.pack('>f', value)` 还原 4 字节 ASCII）
- UTF-16 endianness reversal（utf-16-LE ↔ utf-16-BE）
- Unicode Tags（U+E0000-U+E007F）/ Variation Selector Supplement（U+E0100-U+E01EF）
- Multi-layer auto-decoder（hex 优先于 base64，per ctf-misc/encodings.md）

#### 3.8.4 Base64 隐写（`core/encoders/base64_stego.py` · v0.5+ 新模块）

> **原理**：base64 每字符 6 bit 表示数据，但**末尾不足 3 字节时末 2 bit 是冗余的**（因为只用 12/18 bit = 2/3 字符）。CTF 隐写：把 1 byte 隐藏数据拆成 4 个 2-bit，分别塞进 4 个 base64 字符的**末 2 bit**。解码 = 提取每字符末 2 bit → 4 个 2-bit 拼成 1 byte → 这就是隐藏数据。
>
> **算法实现**：`decode_base64_stego(s)` / `encode_base64_stego(s, hidden)` / `extract_hidden_with_size_hint(s, hint_bytes=N)`
>
> **简化算法**：每字符末 2 bit 都视为可隐藏位 → 4 chars → 1 byte（CTF 常见）。
>
> **GUI 入口**：`decoder:base64-stego` 在 "🔐 Base/ROT 解码" 分类下。
>
> 详细实现 + GUI 入口见 `upgrade/v0.5-base-rot-decoders.md` PR2 / PR3。

**Python 依赖**：

| 包 | 状态 | 用途 | 备注 |
|---|---|---|---|
| **base65536** | ✅ `pip install base65536`（v0.5-base-rot-decoders PR1 完成）| base65536 编解码 | v0.5 已装 |

### 3.9 Misc Others / Archive（压缩包分析）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **7z** | ✅ | `extend-tools/bin/win-x64/7z.exe` | 全格式解压（zip/rar/7z/tar.gz/bz2/xz） | P0 · v0.1 必须 |
| **unzip** | ❌ | `/usr/bin/unzip` | zip 解压 + 伪加密检查 | P0 |
| **file** | ✅ | `extend-tools/bin/win-x64/file.exe` | magic 识别压缩类型 | P0 |
| **john** | ❌ | `brew install john-jumbo` | 4-6 位数字爆破（zip/rar） | P0 · v0.1 必须装 |
| **hashcat** | ❌ | `brew install hashcat` | GPU 加速破解（zip/rar 哈希） | v0.5 安装 |
| **bruteforce_zip (自研)** | ✅ | `core/actions/zip_chain.py:BruteforceZipAction` + `_generate_passwords` | 纯 Python 字典爆破 zip 4-6 位数字 + 4 位字母（≈ 8.4M 组合） | v0.5 自研替代未实现的 zipcrack.py；per [`upgrade/v0.5-zipcrack-doc-update.md`](./upgrade/v0.5-zipcrack-doc-update.md) |
| **rar / unrar** | ❌ | `brew install rar` | rar 创建 / 解压（区别于 unrar-only） | v0.5 安装 |

### 3.10 Misc Others / Office（文档分析）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **exiftool** | ✅ | `extend-tools/bin/win-x64/exiftool.exe` | Office/PDF 元数据 + 隐藏字段 | P0 |
| **binwalk** | ✅ | `python -m binwalk` 文档内嵌文件检测 | P0 |
| **pdftotext** | ❌ | `brew install poppler` 后 `/usr/local/bin/pdftotext` | PDF 文本提取 | v0.1 通过 exiftool + binwalk 间接覆盖，pdftotext 可选 |
| **mutool** | ❌ | `brew install mupdf-tools` | PDF 重组 + 对象提取（xref 隐藏页） | v0.5 安装 |
| **python-docx** | ❌ | `python3 -c "import docx"` ✅ | .docx 解析（XML 结构 + 隐藏文字 + macro） | v0.5 候选 |

### 3.11 Misc Others / Brainteaser（脑洞题）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **Python 标准库** | ❌ | macOS 自带 | 字符串/字符操作 + struct + re | 全部脑洞题 base |
| **z3-solver** | ❌ | `pip install z3-solver` | 约束求解（约束编码 / Boolean gate network） | v0.5 安装 |
| **PIL（Pillow）** | ✅ | `python3 -c "import PIL"` ✅ | 像素级脑洞题（图片当数据） |（已装 Pillow 12.2.0） 已装 Python 包 |
| **qrcode / segno / pyzbar** | ❌ | `pip install qrcode segno pyzbar` | QR 生成 / 解析 / 重组 | v0.5 安装 |

### 3.12 共享基础工具（不挂 subflow · 各分支通用）

| 工具 | 状态 | 路径 / 安装 | 用途 | 备注 |
|---|---|---|---|---|
| **strings** | ✅ | `extend-tools/bin/win-x64/strings.exe` 提取可打印字符串（跨所有 binary 类文件） | P0 · 通用 |
| **file** | ✅ | `extend-tools/bin/win-x64/file.exe` | magic 识别（跨所有文件） | P0 · 通用 |
| **xxd** | ✅ | `extend-tools/bin/win-x64/vim92/xxd.exe` | hex dump / hex ↔ binary | P0 · 通用 |
| **hexdump** | ❌ | `/usr/bin/hexdump` | hex dump（BSD 风格） | P1 · 通用 |
| **Select-String** | ✅ | PowerShell 内置 | 文本搜索（flag / ctf / key） | P0 · 通用 |
| **exiftool** | ✅ | `extend-tools/bin/win-x64/exiftool.exe` | 元数据（跨图片 / Office / 部分 PDF） | P0 · 通用 |
| **foremost** | ✅ | `extend-tools/bin/win-x64/foremost.exe` | 文件雕刻（跨所有 binary 类文件） | P0 · 通用 |
| **scalpel** | ❌ | `brew install scalpel` | 高效文件雕刻（foremost 备选） | v0.5 安装 |

---

## 4. Python 包清单

| 包 | 状态 | 用途 | 备注 |
|---|---|---|---|
| **PIL（Pillow）** | ✅ | 图像读取 + LSB 提取 + 像素脑洞 | P0 |（已装 Pillow 12.2.0）
| **pwn（pwntools）** | ❌ | 通用 CTF 工具库（含 base64/hex/远程交互）| P0 · `pip install pwntools` |
| **lxml** | ✅ | XML 解析（OOXML / Plist / Kitty 协议）| P1 |（已装 lxml 6.1.1）
| **docx（python-docx）** | ✅ | .docx 解析 | P1 |（已装 python-docx 1.2.0）
| **numpy** | ✅ | 数值计算 + 图像处理（频谱 / FFT）| P0 · `pip install numpy` |（已装 numpy 2.3.5）
| **requests** | ✅ | （**保留**：虽然 automisc 不联网，但保留供 CTFd API 等离线场景使用，per [`prd.md §3.3`](./prd.md) 占位说明）| P1 · `pip install requests` |（已装 requests 2.34.2）
| **z3-solver** | ❌ | 约束求解（约束编码 / Boolean gate network）| P0 · `pip install z3-solver` |
| **matplotlib** | ❌ | 频谱图 + 直方图绘图 | P1 · `pip install matplotlib` |
| **scipy** | ✅ | 信号处理 + 频谱分析（FFT / 时频分析）| P1 · `pip install scipy` |（已装 scipy 1.18.0）
| **magic（python-magic-bin）** | ✅ | file 类型识别（macOS 用 `python-magic-bin`）| P0 · `pip install python-magic-bin` |（已装 python-magic 0.4.27）
| **dnslib** | ❌ | DNS 解析（DNS 隐写题 / dnscat2 reassembly）| P1 · `pip install dnslib` |
| **zsteg（**注意：实为 Ruby gem**）** | ✅（PATH） | PNG/BMP LSB（不在 Python 包）| 已在 §3.5 修正 |
| **Crypto（pycryptodome）** | ✅ | 古典密码 + AES/DES | P1 · `pip install pycryptodome` |（已装 pycryptodome 3.23.0）
| **pikepdf** | ❌ | PDF 操作 + 解密 | P1 · `pip install pikepdf` |
| **zstandard** | ✅ | zstd 解压（CTF 偶尔出现）| P1 · `pip install zstandard` |（已装 zstandard 0.25.0）
| **mutagen** | ❌ | 音频元数据 | P1 · `pip install mutagen` |
| **segno / pyzbar / qrcode** | ❌ | QR 生成 / 解析 | P2 · `pip install segno pyzbar qrcode` |
| **stegano / stegolsb / stegcracker** | ❌ | 高级 LSB + 爆破 | P2 · `pip install stegano stegolsb stegcracker` |
| **base65536** | ✅ | base65536 编码 | P1 · `pip install base65536` |（已装 base65536 0.1.1）
| **python-evtx** | ✅ | .evtx 事件日志解析（Python 模块 + adapter `EvtxDumpAdapter` 用 in-process `import Evtx` 做结构化字段访问 + EventID 4625/1102/4688 scoring）| P0 · v0.5 已装 |（已装 python-evtx 0.8.1）|

> **自动检测范围**：v0.1 启动时，Core 调度层应在启动时调用 `check_dependencies()`，对 §6 P0 工具做可达性检查，缺失时 GUI 提示并降级（而非阻塞启动）。

---

## 5. 入口分流与工具路由对照

> 完整入口分流表见 [`prd.md §6`](./prd.md)。本节是分流表 → 工具池的"反向索引"。

| subflow（来自 `prd.md §6`）| 推荐初始工具（来自本文件）| fallback 工具 |
|---|---|---|
| **Memory Forensics** | vol.py + strings + binwalk | vol3 / photorec（雕刻）|
| **Disk Forensics** | 7z（解 VMDK/OVA）+ photorec + testdisk | sleuthkit（fls/icat）/ veracrypt |
| **Network Forensics** | tshark + tcpdump + file | wireshark（GUI 辅助）/ pcapfix / scapy |
| **Log Forensics** | Select-String（PowerShell）+ python-evtx（adapter in-process）| 7z（解压 .evtx.bz2）|
| **Image Stego** | exiftool + zsteg + foremost + binwalk | steghide / outguess / stegdetect / stegseek / F5 |
| **Audio Stego** | ffmpeg（频谱）| sox / audacity / DeepSound / MP3Stego |
| **Video Stego** | ffmpeg + ffprobe（多 stream 提取）| vlc（视觉验证）/ MP4Box / mediainfo |
| **Encoding** | （**内置实现**）`core/encoders/base.py` + `classical.py` + `custom.py` | 全部内置，无外部依赖 |
| **Archive** | 7z + unzip + file + bruteforce_zip（自研 Python 字典爆破）| john（爆破）/ hashcat（GPU 爆破）|
| **Office** | exiftool + binwalk + python-docx | pdftotext / mutool |
| **Brainteaser** | Python 标准库 + z3-solver + Pillow | 全部脑洞题通用 base |
| **未知二进制** | file + strings + binwalk + foremost + xxd | exiftool / scalpel / hexdump |

---

## 6. P0 工具优先级（v0.1 必须有 adapter）

> **依据** [`prd.md §4.1 v0.1.6`](./prd.md)：v0.1 必须落地 **≥5 个 adapter**。
> **当前实际 P0 工具数：23 个**（覆盖全部 11 个 subflow；v2.9 删 evtx_dump #16；v0.5-zipcrack-doc-update 加 bruteforce_zip 自研 #13a）。

### 6.1 P0 工具清单（23 个 · 按 subflow 排列）

| # | 工具 | 分支 / 子分支 | 安装依赖 |
|---|---|---|---|
| 1 | **binwalk** | Stego/Image + Forensics/Memory + 通用 | ✅ 已装（`python -m binwalk`，pip binwalk 2.3.2）|
| 2 | **strings** | Forensics/Memory + 通用 | ✅ 已装（`extend-tools/bin/win-x64/strings.exe`）|
| 3 | **foremost** | Stego/Image + 通用 | ✅ 已装（`extend-tools/bin/win-x64/foremost.exe`）|
| 4 | **exiftool** | Stego/Image + Misc/Office + 通用 | ✅ 已装（`extend-tools/bin/win-x64/exiftool.exe`）|
| 5 | **tshark** | Forensics/Network | ❌ pending |
| 6 | **tcpdump** | Forensics/Network | ❌ pending |
| 7 | **file** | Misc/Archive + 通用 | ✅ 已装（`extend-tools/bin/win-x64/file.exe`）|
| 8 | **7z** | Forensics/Disk + Misc/Archive + Forensics/Log | ✅ 已装（`extend-tools/bin/win-x64/7z.exe`，7zr.exe 同目录 hardlink）|
| 9 | **steghide** | Stego/Image + Stego/Audio | ✅ 已装（`extend-tools/bin/win-x64/steghide/steghide.exe`，cygwin DLL 同目录）|
| 10 | **zsteg** | Stego/Image | ❌ pending（Win 无 Ruby gem；用自研 `lsb_tool` 替代，per [`upgrade/v0.5-lsb-tool-unify.md`](./upgrade/v0.5-lsb-tool-unify.md)，3 mode 统一 LSB 工具 detect/extract/extract_bytes）|
| 11 | **ffmpeg** | Stego/Audio + Stego/Video | ❌ pending |
| 12 | **ffprobe** | Stego/Video | ❌ pending |
| 13 | **unzip** | Misc/Archive | ❌ pending（Win 可走 7z / Python `zipfile` 替代）|
| 13a | **bruteforce_zip (自研)** | Misc/Archive | ✅ 已装（`core/actions/zip_chain.py:BruteforceZipAction` + `_generate_passwords`，纯 stdlib `itertools.product`，8.4M 字典；per [`upgrade/v0.5-zipcrack-doc-update.md`](./upgrade/v0.5-zipcrack-doc-update.md)，Owner 2026-06-28 实战命中 password='7639' tried 7640/8421616）|
| 14 | **xxd** | 通用 | ✅ 已装（`extend-tools/bin/win-x64/vim92/xxd.exe`）|
| 15 | **Select-String** | Forensics/Log + 通用 | ✅ 已装（PowerShell 内置）|
| 16 | **vol.py** | Forensics/Memory | ❌ pending（必须先恢复 vol2 安装）|
| 18 | **john** | Misc/Archive | ❌ pending（Win 用自研 `BruteforceZipAction` Python 字典爆破替代，per [`upgrade/v0.5-zipcrack-doc-update.md`](./upgrade/v0.5-zipcrack-doc-update.md)）|
| 19 | **zbar** | Misc/Brainteaser（QR）| ❌ pending |
| 20 | **sox** | Stego/Audio | ❌ pending |
| 21 | **python-magic-bin** | 通用（file 类型识别 Python）| ❌ pending（pip install 待装）|
| 22 | **numpy** | 通用（图像/频谱处理）| ❌ pending（pip install 待装）|

### 6.2 P0 实施顺序（按 PR 拆分 · per `AGENTS.md §2.1` ≤400 行/PR）

| PR | 任务 | adapter 数 | 依赖 |
|---|---|---|---|
| **v0.1.0b-PR1** | 共享基础工具（binwalk / strings / file / xxd / foremost / exiftool）| 6 | 无 |
| **v0.1.0b-PR2** | Stego/Image 主工具（zsteg / steghide / binwalk 复用）| 2 | 复用 PR1 |
| **v0.1.0b-PR3** | Forensics/Network（tshark / tcpdump）| 2 | 无 |
| **v0.1.0b-PR4** | Stego/Audio+Video（ffmpeg / ffprobe）| 2 | 无 |
| **v0.1.0b-PR5** | Misc/Archive（7z / unzip / john 安装 + adapter）| 3 | 无 |
| **v0.1.0b-PR6** | Forensics/Log（grep / evtx_dump + python-evtx 安装）| 2 | python-evtx 安装 |
| **v0.1.0b-PR7** | Forensics/Memory（vol.py 恢复 + adapter）| 1 | vol.py 恢复安装（blocker） |
| **v0.1.0b-PR8** | Misc/Brainteaser QR（zbar 安装 + adapter）| 1 | zbar 安装 |
| **v0.1.0b-PR9** | Python 包：python-magic-bin + numpy 安装 + 基础依赖 | 3 | pip 安装 |

> **判断**：v0.1 阶段 21 个 P0 adapter 分 9 个 PR，平均每 PR 2-3 个 adapter，远低于 400 行限制。

### 6.3 Encoding（自编写）的 P0 实现

| 模块 | 内容 | 估时 |
|---|---|---|
| `core/encoders/base.py` | base16/32/58/62/64/85/91 + base2048/32768/65536 | 2h |
| `core/encoders/classical.py` | ROT13/47/18 + Caesar brute force + Vigenère + Atbash + Pigpen + Keyboard Shift + Affine + Rail Fence | 3h |
| `core/encoders/custom.py` | BCD + IEEE 754 + UTF-16 endianness + Unicode Tags + Variation Selector + Multi-layer auto-decoder | 3h |
| `core/encoders/__init__.py` + unit test | 注册 + 测试 | 1h |
| **小计** | | **9h** |

> Encoding 不算 adapter，是 Core 内部能力，**不计入 §6.2 P0 PR 拆分**。

---

## 7. 工具池后续演进

### 7.1 v0.5（per [`prd.md §10.2`](./prd.md)）

- P1 工具批量追加：outguess / stegdetect / stegseek / pngcheck / sleuthkit / pcapfix / aircrack-ng / multimon-ng / scapy / impacket / hashcat / mutool / python-evtx / sox / audacity / sonic-visualiser / vlc / MP4Box / mediainfo / zbar / qrencode / apngdis / scalpel
- Python 包补齐：numpy / requests / matplotlib / scipy / python-magic-bin / dnslib / pycryptodome / pikepdf / zstandard / mutagen / base65536 / z3-solver / segno / pyzbar / qrcode / stegano / stegolsb / stegcracker

### 7.2 v1.0（per [`prd.md §10.3`](./prd.md)）

- DAG 编排要求工具输出**结构化 type system**（per [`Architecture.md §9.1`](./Architecture.md) 兼容点）
- 每个 adapter 补 `outputs: list[str]` 字段（per [`Architecture.md §9.2`](./Architecture.md)）
- DeepSound + Wine 集成评估（macOS 上的可行性）
- Encoding 子模块补全：RSA / AES / SM4 / Brainfuck / Ook! / Malbolge / Piet（per ctf-misc/encodings.md）

---

## 8. 变更日志

> **维护策略**：本表只保留**最近 4 条**。超出范围旧条目归档到 `docs/changelog/tools.md_archived.md`（v0.1+ 创建）。
> 当前 10 条（历史归档滞后，待后续 v0.5+ 维护 PR 一次性归档 2.0~2.5 旧条目）。

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-06-29 | **2.11** | **v0.5-lsb-tool-unify 落地 + §3.5/§6.1 lsb_tool 行** (per Owner 2026-06-28 10:40 全批准 + 5 commits 2904a3b/5cba63a/d5de9ed/2f6825d/b7b212c): §3.5 Steganography/Image 加 **lsb_tool** 行（✅ 自研 Python, 3 mode 统一 LSB 工具 detect/extract/extract_bytes, 替代 zsteg + lsb_detect + lsb_extract + lsb_bytes_extract; per `upgrade/v0.5-lsb-tool-unify.md`）; §6.1 P0 #10 zsteg 备注更新: `lsb_detect` → `lsb_tool` + 链接到 `upgrade/v0.5-lsb-tool-unify.md`; §8 v2.11 changelog 加本条。**Scope 范围**: Phase 1 spec + Phase 2a detect mode + Phase 2b extract/extract_bytes mode + Phase 3 adapter + Phase 4 GUI dialog 合并（lsb_bytes_dialog + lsb_extract 按钮 → lsb_tool_dialog + lsb_tool 按钮，9 参数）; Phase 5 本次 docs 同步; Phase 6 老 action deprecated 标记 + Phase 7 实战 regression 待办。**不动 §2 总表数字**: lsb_tool 是 Python 实现无独立 binary, 不增 "21→22"; lsb_detect / lsb_extract / lsb_bytes_extract 仍是 P0 adapter 但功能合并到 lsb_tool（仍注册 backward compat, Phase 6 才 deprecated）。详见 [`upgrade/v0.5-lsb-tool-unify.md`](./upgrade/v0.5-lsb-tool-unify.md)。 |
| 2026-06-28 | **2.10** | **§3.4 python-evtx ❌→✅ + requirements.txt 文档同步** (per Owner 2026-06-28 "更新 python-evtx 在 tools.md 的状态, 并且加入requirements.txt"): §3.4 python-evtx 行状态 ❌→✅ + 路径列加 `requirements.txt` 第 12 行 pinned 说明; §2 总表 Forensics 2✅/12❌ → 3✅/11❌ + 合计 18✅/36❌ → 19✅/35❌; §2 备注 header 加 v2.10 引用。**requirements.txt 不动**: `python-evtx==0.8.1` 已在 v2.7 commit (`b8e5241`) 加入第 12 行 + 注释 `>=0.8.1`, 无需重复添加（`pip show python-evtx` 验证 0.8.1 已装）。§6.1 P0 列表不动: python-evtx 是 Python 包不是外部工具, 不进 §6.1 P0 22→21 范围。详见 §3.4 + `requirements.txt`。 |
| 2026-06-28 | **2.9** | **§3.4 evtx_dump 整段删除** (per Owner 2026-06-28 "是否可以删除 tools.md 中3.4 evtx_dump"): §3.4 表格删 evtx_dump 行（剩 Select-String + python-evtx + 7z + journalctl 4 项）+ 删 §3.4.1 (参数速查表 14 参数) + 删 §3.4.2 (典型调用 5 pattern) + 删 §3.4.3 (adapter 封装模板 + 决策点表); §3.4.4 (python-evtx Python 模块用法) → 重编号 §3.4.1 + 删 "CLI vs Python 路径分工" 段（CLI 文档全删, 这段成空头）; §5 subflow 表 Log Forensics 行 `Select-String + evtx_dump \| 7z + python-evtx` → `Select-String + python-evtx (adapter in-process) \| 7z`; §6.1 P0 #16 evtx_dump 行删除（21 个 P0 工具, 不是 22 个）; 5 处 "22 个" → "21 个" 同步 (§2 备注 / §6 header / §6.1 / §6.2 / §6 header); §3.4 表格底加 evtx_dump CLI 撤回说明脚注（指 upgrade/v0.5-windows-evtx-dump.md §6）。**不动**: python-evtx 行状态仍 ❌（虽然已装且 adapter 在用, Owner 未拍板 ✅ 切换; 留 §8 v2.10 跟进）。详见 [`upgrade/v0.5-windows-evtx-dump.md`](./upgrade/v0.5-windows-evtx-dump.md)。 |
| 2026-06-28 | **2.8** | **scope 收窄** (per Owner 2026-06-28 "既然python-evtx能代替 evtx-dump"): `extend-tools/install.ps1` 加 **Stage 0 Rust toolchain 装** (rustup-init stable + minimal profile, 失败 warning continue, idempotent 跳过已装) — **保留**（独立价值：未来 cargo install / binwalk v3 备选 / ad-hoc 工具）；**Stage 1 evtx_dump CLI 撤回** — 不加 evtx_dump 到 `$binaries` 数组。决策依据：adapter `src/automisc/tools/forensics/log/evtx_dump.py` 用 `python-evtx` 0.8.1 实现结构化字段访问 (XPath `e:System/e:EventID` / `e:EventData/e:Data[@Name='CommandLine']`) + EventID scoring (4625/1102 → sev 5) + 命令行关键字匹配 (powershell/cmd/mimikatz/-enc), evtx_dump CLI 在 adapter 路径上 0 调用, 实际价值仅 = Owner 手动 `evtx_dump file.evtx | grep flag` 的便利 (可被 5 行 Python one-liner 替代); 实战 ≥3 道同类命中再升架构 per AGENTS §5.2 防单题打补丁。`extend-tools/manifest.yaml` v1.2 → v1.1 回滚 (evtx_dump 块删除); §3.4/§3.4.1/§3.4.3/§3.4.4/§4/§6.1#16 evtx_dump 路径全部回滚到 `extend_tools/evtx_dump` (legacy macOS 软链, 当前 Win 未生效); §2 总表 19✅/35❌ → 18✅/36❌ (Forensics 3✅→2✅)。原 commit `f54d859` 的 smoke 9 测 + SHA256 校验结果作为"已验证，待实战触发再启用"证据保留在 `upgrade/v0.5-windows-evtx-dump.md` §6 决策记录。详见 [`upgrade/v0.5-windows-evtx-dump.md`](./upgrade/v0.5-windows-evtx-dump.md)。 |
| 2026-06-28 | **2.7** | **§3 strings + binwalk + grep→Select-String + §4 Python 包同步** (per Owner 2026-06-28 指令): Owner 实装 `strings.exe` 到 `extend-tools/bin/win-x64/strings.exe` (370KB, 2026-06-27) + `pip install binwalk 2.3.2` 已在 venv (注意: pip freeze 显示从 `automisc/extend-tools/bin/win-x64/binwalk-2.3.2` 本地路径安装, 老目录残留, 需清); §3 strings/binwalk 标 ✅; §3 + §6.1 `grep` 替换为 PowerShell `Select-String` (Win 替代, awk/sed/sort/uniq 仍 pending); §4 Python 包: PIL/lxml/docx/numpy/scipy/python-magic/pycryptodome/zstandard/base65536/python-evtx 已装, 12+ 包仍 pending; 新增 `requirements.txt` (pinned 版本, 从 pip freeze 提取 + pyproject.toml 对齐); §2 统计刷新 (18✅ / 36❌ pending)。 |
| 2026-06-28 | **2.6** | **§3 + §6.1 状态同步**：Owner 在 `extend-tools/bin/win-x64/` 实装 8 个二进制（`file.exe` / `7z.exe` + `7zr.exe` / `exiftool.exe` / `foremost.exe` / `vim92/diff.exe` / `vim92/xxd.exe` / `steghide/steghide.exe`），对应 §3 / §6.1 表格行已标 ✅ + Windows extend-tools 路径；其他工具统一标 ❌ (pending)。同步由 `tools_status_sync.py` 脚本完成（单文件，不入 commit）。 |
| 2026-06-27 | **2.5** | v0.5-windows-only 治理变更 v3.3：项目定位收窄为 Windows only（per `AGENTS.md §2.3`）；`extend-tools/bin/win-x64/` 是 Win 优先工具链；macOS / Linux 路径探测代码 + brew 注释清理待 PR5/6 实施；详见 [`upgrade/v0.5-windows-only.md`](./upgrade/v0.5-windows-only.md)。 |
| 2026-06-13 | 1.0 | 初版：扫描 9 个 subflow + macOS 工具抽查。详见 git history。 |
| 2026-06-13 | **2.0** | 重大分支重整：从 9 subflow 改为 11 subflow（Forensics×4 + Stego×3 + Encoding×3 + Misc Others×3）；54 工具（28✅/2⚠️/24❌）；Encoding 内置实现。详见 commit `9401f98`。 |
| 2026-06-13 | **2.1** | v0.1.0b-PR1 实施完成：6 个共享 adapter 落地（61 tests PASS）。详见 commit `9401f98`。 |
| 2026-06-13 | **2.2** | v0.1.0b-PR2 实施完成：Stego/Image 2 个 adapter 落地（75 tests PASS）。详见 commit `4ca05e5`（PR #2）。 |
| 2026-06-14 | **2.3** | v0.5-tool-install-batch-1：4 个工具❌→✅（pcapfix / aircrack-ng / scapy / impacket）；python-evtx ❌→⚠️。详见 [`upgrade/v0.5-tool-install-batch-1.md`](./upgrade/v0.5-tool-install-batch-1.md)。 |
| 2026-06-14 | **2.4** | v0.5-tool-install-batch-2：sox ❌→✅（brew install）；evtx_dump ⚠️→✅（`extend_tools/evtx_dump` Rust 0.8.2，跟 python-evtx 是不同项目）；python-evtx ⚠️→✅。详见 [`upgrade/v0.5-tool-install-batch-2.md`](./upgrade/v0.5-tool-install-batch-2.md)。 |

---

> **最后一条**：
> 本文档是 automisc 工具池的**单一事实来源**。任何"我要装什么 / 缺什么 / 怎么调"问题先查这里。
> 任务看板在 [`prd.md §3`](./prd.md) + adapter 实现规范在 [`Architecture.md §6`](./Architecture.md)。